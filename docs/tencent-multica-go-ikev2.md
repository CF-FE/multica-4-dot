# 腾讯云 Multica Go 与 iPhone IKEv2 运维手册

适用于腾讯云 `/opt/multica` 自托管实例。iPhone 使用系统内置 IKEv2，VPN 只把发往 Multica 私网地址的流量送进隧道。服务端按端口限制访问。2026-11-24 已验证实际 iPhone 建隧道、获取验证码并成功登录 Multica Go。

## 部署基线

| 项目 | 2026-11-24 实测配置 |
| --- | --- |
| 腾讯云主机 | `VM-0-9-ubuntu`，Ubuntu 26.04，`eth0` 私网地址 `10.0.0.9` |
| IKEv2 入口 | 公网 IPv4 `43.143.70.108`，UDP `500` 和 `4500` |
| VPN 服务 | strongSwan `6.0.4-1ubuntu3.2`，`strongswan.service` 已启用 |
| VPN 客户端地址池 | `10.88.248.0/29`，手机实际分到 `10.88.248.1` |
| 隧道目标 | `10.207.56.3/32`，只放行 TCP `3000,8080` |
| Multica Go API 地址 | `http://10.207.56.3:8080` |
| Multica Go Web 平台地址 | `http://10.207.56.3:3000` |
| Multica | `v0.12.1`，前后端发布到回环和 EasyTier 地址，PostgreSQL 在 Compose 网络内 |
| VPN 认证 | 服务器证书由专用 CA 签发，手机以独立 EAP-MSCHAPv2 账号登录 |
| 当前服务器证书 | SAN 为 `IP:43.143.70.108`，到期时间为 2027-11-24 22:33（北京时间） |

Multica Go 的两个地址都是隧道内的 HTTP 端点，外层由 IKEv2/IPsec 加密。手机的其余流量继续使用原来的 Wi-Fi 或蜂窝网络。新增公网入站规则限于 VPN 的两个 UDP 端口。 [strongSwan 分流说明](https://docs.strongswan.org/docs/6.0/howtos/forwarding.html) · [Multica Go 服务器配置](https://multica.1991421.cn/docs/servers-workspaces/)

## 重建

以下示例沿用实测地址。更换主机前，确认新的公网 IP、VPC 接口地址、EasyTier 地址和地址池，按文末联动表更新。应用实例和数据卷的恢复沿用[腾讯云 Multica 升级手册](tencent-upgrade.md)。

### 1. 核对宿主机和安全组

确认 EasyTier 地址已出现、Docker 在该地址提供两个本地 TCP 监听、Multica API 就绪、UDP `500/4500` 空闲。若已有 VPN 服务，先查现有配置和在线会话，避免重复部署。

~~~bash
ip -br -4 address
ip -4 route show table main
sudo ss -H -lunp '( sport = :500 or sport = :4500 )'
sudo ss -H -ltnp '( sport = :3000 or sport = :8080 )'
curl --noproxy '*' -fsS http://10.207.56.3:8080/readyz
curl --noproxy '*' -fsS -o /dev/null -w '%{http_code}\n' http://10.207.56.3:3000/
~~~

腾讯云实例安全组新增 UDP `500` 和 `4500` 入站。手机在蜂窝网络下源 IP 会变化，本次两条规则允许 IPv4 `0.0.0.0/0`，访问授权由 IKEv2 完成。云端公网 IPv4 映射到 `10.0.0.9`，配置内的 `encap = yes` 强制 ESP 使用 UDP 封装。 [腾讯云安全组说明](https://cloud.tencent.com/document/product/213/112610) · [strongSwan 连接配置](https://docs.strongswan.org/docs/6.0/swanctl/swanctlConf.html)

### 2. 准备证书和账号

已有可信备份时，按下一节的路径恢复证书、服务端私钥和账号配置。复用同一 CA、服务器身份和密码，手机可以继续使用原描述文件。

首次重建且没有 CA 时，在可信运维机的 Bash 中执行以下命令。本次使用专用 CA，服务器证书只用于公网 IPv4 上的 IKEv2 服务。手机描述文件包含 CA 证书和 VPN 登录凭据。 [strongSwan 的 iOS 证书要求](https://docs.strongswan.org/docs/6.0/interop/ios.html)

~~~bash
set -euo pipefail
umask 077
VPN_WORK="$(mktemp -d "${TMPDIR:-/tmp}/multica-ikev2.XXXXXXXX")"
export VPN_WORK
export VPN_PUBLIC_IP=43.143.70.108
export VPN_USER=multica-iphone
export VPN_CA_NAME='Multica iPhone VPN CA'

cat > "$VPN_WORK/ca.cnf" <<EOF
[req]
distinguished_name = name
x509_extensions = root
prompt = no
[name]
CN = $VPN_CA_NAME
[root]
basicConstraints = critical,CA:true,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
EOF

cat > "$VPN_WORK/server.ext" <<EOF
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = IP:$VPN_PUBLIC_IP
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
EOF

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$VPN_WORK/ca-key.pem"
openssl req -new -x509 -sha256 -days 1825 -config "$VPN_WORK/ca.cnf" \
  -key "$VPN_WORK/ca-key.pem" -out "$VPN_WORK/ca.pem"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$VPN_WORK/server-key.pem"
openssl req -new -key "$VPN_WORK/server-key.pem" -subj "/CN=$VPN_PUBLIC_IP" \
  -out "$VPN_WORK/server.csr"
openssl x509 -req -in "$VPN_WORK/server.csr" -CA "$VPN_WORK/ca.pem" \
  -CAkey "$VPN_WORK/ca-key.pem" -set_serial "0x$(openssl rand -hex 16)" \
  -days 365 -sha256 -extfile "$VPN_WORK/server.ext" -out "$VPN_WORK/server.pem"
openssl verify -CAfile "$VPN_WORK/ca.pem" -verify_ip "$VPN_PUBLIC_IP" \
  -purpose sslserver "$VPN_WORK/server.pem"
openssl rand -hex 24 > "$VPN_WORK/eap-password"
~~~

通过已验证的 SSH 运维入口，将 `ca.pem`、`server.pem`、`server-key.pem` 安全传到主机的私有暂存目录。把 `eap-password` 的值写入连接配置中的密码字段，生成手机描述文件时复用同一个值。CA 私钥保存在运维端受控密钥库，主机只需要 CA 证书。证书私钥、含密码的配置和手机描述文件均以私密方式保管。

### 3. 安装 strongSwan 并加载配置

以下命令在腾讯云主机执行。首次部署时在安装之前临时遮蔽服务单元，完成配置与防火墙后再解除。

~~~bash
sudo systemctl mask --runtime strongswan.service
sudo apt-get install charon-systemd strongswan-swanctl strongswan-pki \
  libcharon-extra-plugins libstrongswan-extra-plugins
~~~

| 内容 | 安装位置 | 权限 |
| --- | --- | --- |
| CA 证书 `ca.pem` | `/etc/swanctl/x509ca/multica-iphone-ca.pem` | `0644` |
| 服务器证书 `server.pem` | `/etc/swanctl/x509/multica-iphone-server.pem` | `0644` |
| 服务器私钥 `server-key.pem` | `/etc/swanctl/private/multica-iphone-server-key.pem` | `0600` |
| 连接、地址池和 EAP 密码 | `/etc/swanctl/conf.d/multica-iphone.conf` | `0600` |

以 `root:root` 安装上述文件。主配置 `/etc/swanctl/swanctl.conf` 通过 `include conf.d/*.conf` 读取连接。用私密编辑器把下面的占位符换成生成的随机密码再启用服务。

~~~text
connections {
    multica-iphone {
        version = 2
        local_addrs = 10.0.0.9
        encap = yes
        send_cert = always
        proposals = aes256-sha256-prfsha256-modp2048
        pools = multica-iphone
        fragmentation = yes
        dpd_delay = 30s
        local {
            auth = pubkey
            id = 43.143.70.108
            certs = multica-iphone-server.pem
        }
        remote {
            auth = eap-mschapv2
            eap_id = multica-iphone
        }
        children {
            multica-private {
                local_ts = 10.207.56.3/32
                esp_proposals = aes256-sha256
                dpd_action = clear
            }
        }
    }
}
pools {
    multica-iphone {
        addrs = 10.88.248.0/29
    }
}
secrets {
    eap-multica-iphone {
        id = multica-iphone
        secret = "__REPLACE_WITH_GENERATED_EAP_PASSWORD__"
    }
}
~~~

### 4. 安装 VPN 专用防火墙

`local_ts` 将隧道目标限定为单个 IP。主机防火墙检查来源地址池和入站 IPsec 策略，只放行 `3000` 和 `8080`。这两端口使用 Docker 在宿主上的本地监听。VPN 流量在 NAT PREROUTING 阶段保留原始目标，交给对应的 `docker-proxy` 监听，避免 Docker 先做 DNAT。重建时应核对 Docker 的本地监听仍存在。 [strongSwan 关于 NAT 的说明](https://docs.strongswan.org/docs/6.0/howtos/forwarding.html#_general_nat_problems) · [Docker 端口发布说明](https://docs.docker.com/engine/network/port-publishing/)

将下列脚本安装为 `/usr/local/sbin/multica-ikev2-filter`，权限 `0755`。规则通过独有注释定位，停止时按原条件删除。

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail

pool=10.88.248.0/29
target=10.207.56.3/32
tag=multica-ikev2
tunnel=(-s "$pool" -m policy --dir in --pol ipsec -m comment --comment "$tag")
access=(-d "$target" -p tcp -m multiport --dports 3000,8080)

add_rule() {
    local table=$1 chain=$2
    shift 2
    iptables -w 5 -t "$table" -C "$chain" "$@" 2>/dev/null ||
        iptables -w 5 -t "$table" -I "$chain" 1 "$@"
}

remove_rule() {
    local table=$1 chain=$2
    shift 2
    if iptables -w 5 -t "$table" -C "$chain" "$@" 2>/dev/null; then
        iptables -w 5 -t "$table" -D "$chain" "$@"
    fi
}

remove_rules() {
    remove_rule filter INPUT "${tunnel[@]}" "${access[@]}" -j ACCEPT
    remove_rule nat PREROUTING "${tunnel[@]}" "${access[@]}" -j ACCEPT
    remove_rule filter INPUT "${tunnel[@]}" -j DROP
    remove_rule filter FORWARD "${tunnel[@]}" -j DROP
}

case "$1" in
    start)
        trap remove_rules ERR
        add_rule filter FORWARD "${tunnel[@]}" -j DROP
        add_rule filter INPUT "${tunnel[@]}" -j DROP
        add_rule nat PREROUTING "${tunnel[@]}" "${access[@]}" -j ACCEPT
        add_rule filter INPUT "${tunnel[@]}" "${access[@]}" -j ACCEPT
        ;;
    stop)
        remove_rules
        ;;
    *)
        exit 2
        ;;
esac
~~~

写入 `/etc/systemd/system/multica-ikev2-filter.service`。

~~~ini
[Unit]
Description=Limit the Multica iPhone VPN to the API and web listeners
After=docker.service
Before=strongswan.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/multica-ikev2-filter start
ExecStop=/usr/local/sbin/multica-ikev2-filter stop
~~~

写入 `/etc/systemd/system/strongswan.service.d/20-multica-ikev2-filter.conf`，使 IKEv2 服务依赖专用防火墙。

~~~ini
[Unit]
Requires=multica-ikev2-filter.service
After=multica-ikev2-filter.service
~~~

~~~bash
sudo bash -n /usr/local/sbin/multica-ikev2-filter &&
  sudo grep -Eq '^[[:space:]]+secret = "[0-9a-f]{48}"$' \
  /etc/swanctl/conf.d/multica-iphone.conf &&
  sudo systemctl unmask --runtime strongswan.service &&
  sudo systemctl daemon-reload &&
  sudo systemctl enable --now strongswan.service &&
  sudo systemctl is-active strongswan.service multica-ikev2-filter.service &&
  sudo swanctl --list-conns &&
  sudo ss -H -lun '( sport = :500 or sport = :4500 )'
~~~

### 5. 生成 iPhone 描述文件

复用第 2 节运维机的目录和环境变量。恢复旧凭据时，在同样的私有目录放置可信备份的 `ca.pem` 和当前 `eap-password`，再生成描述文件。以下模板沿用真机登录时使用的参数。

~~~bash
umask 077
openssl x509 -in "$VPN_WORK/ca.pem" -outform DER -out "$VPN_WORK/ca.der"
python3 - <<'PY'
import os
import plistlib
import uuid
from pathlib import Path

work = Path(os.environ["VPN_WORK"])
server = os.environ["VPN_PUBLIC_IP"]
user = os.environ["VPN_USER"]
ca_name = os.environ["VPN_CA_NAME"]
password = (work / "eap-password").read_text().strip()

def payload(kind, suffix, name):
    return {
        "PayloadType": kind,
        "PayloadVersion": 1,
        "PayloadIdentifier": f"local.multica.iphone-vpn.{suffix}",
        "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadDisplayName": name,
    }

def security_parameters(lifetime_minutes):
    return {
        "EncryptionAlgorithm": "AES-256",
        "IntegrityAlgorithm": "SHA2-256",
        "DiffieHellmanGroup": 14,
        "LifeTimeInMinutes": lifetime_minutes,
    }

ca = payload("com.apple.security.root", "ca", ca_name)
ca["PayloadContent"] = (work / "ca.der").read_bytes()
ca["PayloadCertificateFileName"] = "Multica-iPhone-VPN-CA.cer"

vpn = payload("com.apple.vpn.managed", "ikev2", "Multica 私网")
vpn.update({
    "UserDefinedName": "Multica 私网",
    "VPNType": "IKEv2",
    "IKEv2": {
        "RemoteAddress": server,
        "RemoteIdentifier": server,
        "LocalIdentifier": user,
        "AuthenticationMethod": "Certificate",
        "ExtendedAuthEnabled": 1,
        "AuthName": user,
        "AuthPassword": password,
        "ServerCertificateIssuerCommonName": ca_name,
        "ServerCertificateCommonName": server,
        "EnablePFS": 0,
        "IKESecurityAssociationParameters": security_parameters(1440),
        "ChildSecurityAssociationParameters": security_parameters(60),
    },
})

profile = payload("Configuration", "profile", "Multica iPhone VPN")
profile["PayloadOrganization"] = "Multica 私有部署"
profile["PayloadContent"] = [ca, vpn]
with (work / "Multica-iPhone-VPN.mobileconfig").open("wb") as output:
    plistlib.dump(profile, output, sort_keys=False)
PY
plutil -lint "$VPN_WORK/Multica-iPhone-VPN.mobileconfig"
~~~

用 AirDrop 把文件交给对应 iPhone，在「设置 → 通用 → VPN 与设备管理」安装，然后连接「Multica 私网」。描述文件含登录密码，按凭据管理。 [Apple IKEv2 参数](https://developer.apple.com/documentation/devicemanagement/vpn/ikev2-data.dictionary) · [strongSwan 描述文件示例](https://docs.strongswan.org/docs/6.0/interop/appleIkev2Profile.html)

## 验收与故障定位

1. **VPN 会话**。用 `sudo swanctl --list-sas --ike multica-iphone` 查 `ESTABLISHED` 和 `INSTALLED`。服务端记录的隧道目标应为 `10.207.56.3/32`，手机应拿到 `10.88.248.0/29` 中的地址。双向计数为零时，让手机访问目标地址后重查。 [swanctl 状态说明](https://docs.strongswan.org/docs/6.0/swanctl/swanctlListSas.html)
2. **手机蜂窝网络**。关 Wi-Fi 连 VPN，从手机打开 [API 健康检查](http://10.207.56.3:8080/readyz) 和 [Web 页面](http://10.207.56.3:3000/)。API 应返回 `status: ok`，Web 应能加载。重查隧道双向包数，再用 Multica Go 登录并选择 `cloud-work` 工作区。
3. **访问范围**。服务器侧检查 VPN 的 INPUT、FORWARD 和 NAT 规则。2026-11-24 用独立 Linux 客户端验证了实际 IKEv2 握手、API 就绪、Web HTTP 200 和 TCP 22 拦截，真实 iPhone 后续完成了登录。
4. **新实例登录**。若未配置邮件服务，按既有 Multica 自托管流程由运维查看对应账号的最新验证码，仅通过授权渠道交付该条验证码。 [Multica 自托管登录](https://multica.ai/docs/self-host-quickstart)

~~~bash
sudo swanctl --list-sas --ike multica-iphone
sudo journalctl -u strongswan.service -u multica-ikev2-filter.service --since '-10 min' --no-pager
sudo iptables -nvxL INPUT | awk '/multica-ikev2/'
sudo iptables -nvxL FORWARD | awk '/multica-ikev2/'
sudo iptables -t nat -nvxL PREROUTING | awk '/multica-ikev2/'
~~~

| 现象 | 排查入口 |
| --- | --- |
| 手机发起连接，服务端没看到握手 | 核对公网 IP、实例绑定的安全组和 UDP `500/4500` 监听 |
| IKEv2 认证失败 | 查服务端证书有效期、SAN、iPhone 证书信任、双方账号与密码 |
| IKEv2 已连接，页面打不开 | 手机先访问私网的 `/readyz`，结合 SA 计数和防火墙计数判断是否进了隧道。再核对两个 Docker 本地监听 |
| 网页可访问，Multica Go 报错 | 分别核对 API、Web 字段和请求的账号，按需查 Multica 后端日志 |
| VPN 管理工具连不上 | 查 `systemctl status strongswan.service` 和 `/run/charon.vici`。测试第二个守护进程时隔离运行目录和网络，避免占用生产管理套接字 |

## 更新、撤销与回退

| 变更 | 操作 |
| --- | --- |
| 升级 Multica | 沿 [腾讯云 Multica 升级手册](tencent-upgrade.md) 操作，读回实际绑定的 API/Web 地址，再从手机 VPN 重验 `/readyz`、Web 和 App 登录 |
| 更新 strongSwan | 先备份本手册列出的配置、服务端证书和私钥。看在线会话，安排维护窗口，再更新已安装的包。重查服务依赖、端口监听、真实隧道和 App 登录 |
| 续签服务器证书 | 用现有 CA 和当前公网身份签发新证书，用 `openssl verify -CAfile … -verify_ip … -purpose sslserver …` 验证后替换证书及对应私钥。提前 30 天用 `openssl x509 -checkend 2592000 -noout -in …` 检查期限。使用同一 CA、服务器身份和密码时，手机沿用原描述文件 |
| 手机丢失或密码轮换 | 修改 `multica-iphone.conf` 中的密码，重启 `strongswan.service` 使旧会话结束并加载新凭据，为保留的手机生成新描述文件 |
| 公网 IP 或 VPC 地址变化 | 公网 IP 对应证书 SAN、`local.id` 和 iPhone 的服务器及远程 ID。VPC 地址对应 `local_addrs`。同时核对新实例安全组 |
| EasyTier 地址、地址池或端口变化 | 联动修改隧道目标、地址池、过滤脚本、Compose 绑定及 Multica Go 字段。改动过滤脚本时按下述顺序停旧服务和原规则，再启用新配置 |

对证书或连接配置做更新前，先备份文件并核对在线会话。当前为单手机连接，重启 VPN 会让该设备重连。应用服务仍由自己的 Compose 生命周期管理。过滤规则更新应先用旧脚本的停止动作卸载原规则。

~~~bash
sudo systemctl stop strongswan.service
sudo systemctl stop multica-ikev2-filter.service
# 应用已审批的新配置，或换回已验证备份。
sudo systemctl daemon-reload
sudo systemctl start strongswan.service
sudo systemctl is-active strongswan.service multica-ikev2-filter.service
~~~

如需停用 VPN，执行 `sudo systemctl disable --now strongswan.service`，再执行 `sudo systemctl stop multica-ikev2-filter.service` 并核查带 `multica-ikev2` 注释的规则已经移除。腾讯云控制台撤回该实例为 VPN 新增的 UDP 入站规则。

### 重建所需的私密备份

运维端保存 CA 私钥及证书、服务器证书及私钥、当前 EAP 密码或其密钥库条目。主机文件位置见安装表，防火墙脚本和 systemd 配置见本手册。描述文件可由对应 CA 证书及当前凭据重新生成。交接时记录持有人、备份位置和证书到期日。

2026-11-24 复核时，部署用的 CA 私钥仍在运维 Mac 的权限受限临时目录，可恢复的持久备份尚待确认。在清理临时目录前，将 CA 私钥交由授权的运维密钥库保管并验证可取回。若日后需要换 CA，给手机重发包含新 CA 的描述文件。
