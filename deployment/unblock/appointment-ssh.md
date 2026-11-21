# 协调员任命的只读 SSH 入口

腾讯的 `multica-unblock` 服务账号沿 EasyTier 从 `10.207.56.3` 访问 Vultr 的 `10.207.56.1:22`。Vultr 端读取网关的正式登记，核对磁盘与运行配置一致，再返回工作区 ID、协调员 ID 和已确认的运行代际。

## 腾讯

在腾讯本机为 `multica-unblock` 生成独立 Ed25519 密钥，将私钥留在 `/etc/multica-unblock/appointment-ssh/identity`，归 `multica-unblock:multica-unblock`，权限 `0600`。该目录归 `root:multica-unblock`，权限 `0750`。通过已有受信的 Vultr 运维连接取得服务器 Ed25519 公钥，以 `unblock-appointment-vultr ssh-ed25519 <服务器公钥>` 写入 `known_hosts`。该文件和 `/etc/multica-unblock/appointment-ssh.conf` 均归 `root:multica-unblock`，权限 `0640`。

```sshconfig
Host unblock-appointment
    HostName 10.207.56.1
    BindAddress 10.207.56.3
    User multica-appointment-reader
    Port 22
    AddressFamily inet
    IdentityFile /etc/multica-unblock/appointment-ssh/identity
    IdentitiesOnly yes
    IdentityAgent none
    HostKeyAlgorithms ssh-ed25519
    HostKeyAlias unblock-appointment-vultr
    UserKnownHostsFile /etc/multica-unblock/appointment-ssh/known_hosts
    GlobalKnownHostsFile /dev/null
    StrictHostKeyChecking yes
    UpdateHostKeys no
    BatchMode yes
    PreferredAuthentications publickey
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    GSSAPIAuthentication no
    ClearAllForwardings yes
    ForwardAgent no
    ForwardX11 no
    ControlMaster no
    ControlPersist no
    ControlPath none
    PermitLocalCommand no
    RequestTTY no
    StdinNull yes
    ConnectionAttempts 1
    ConnectTimeout 4
    ServerAliveInterval 3
    ServerAliveCountMax 1
    LogLevel ERROR
```

## Vultr

1. 将 SSH 入口安装到 `/usr/local/sbin/multica-unblock-appointment-ssh`，归 `root:root`，权限 `0755`。将任命读取程序安装到 `/opt/multica-backend/read-appointment.py`，归 `root:root`，权限 `0644`。[SSH 入口](appointment-ssh-entry.py) · [任命读取程序](read-appointment.py)
2. 创建独立系统账号 `multica-appointment-reader`，将登录入口设为上述 SSH 入口，锁定账号密码。账号主目录 `/var/lib/multica-appointment-reader` 及其 `.ssh` 归 `root:root`，权限 `0755`。以腾讯端专用公钥生成 `.ssh/authorized_keys`，归 `root:root`，权限 `0644`。

   ```text
   from="10.207.56.3",restrict,command="/usr/local/sbin/multica-unblock-appointment-ssh" ssh-ed25519 <腾讯专用公钥>
   ```

3. 在 `/etc/sudoers.d/98-multica-appointment-reader` 增加下行，归 `root:root`，权限 `0440`，通过 `visudo -c` 后确认此账号无其他 sudo 授权。

   ```sudoers
   multica-appointment-reader ALL=(root) NOPASSWD: /usr/bin/python3 -I /opt/multica-backend/read-appointment.py
   ```

4. 将已授权的工作区 UUID 写入 `/etc/multica-backend/unblock-reader-workspaces.json` 的 JSON 数组。生产目前登记 `["e25be43b-82b6-419d-9085-bb5c5700b1af"]`。文件归 `root:root`，权限 `0600`。

在腾讯使用服务账号运行下列命令。将工作区换成未授权 UUID 时应返回任命未确认。传入 `id` 或不提供命令时应退出 64。

```sh
sudo -u multica-unblock ssh -F /etc/multica-unblock/appointment-ssh.conf \
  unblock-appointment read-appointment tencent e25be43b-82b6-419d-9085-bb5c5700b1af
```

撤销单个工作区时从 Vultr 白名单移除对应 UUID。撤销整个身份时移出该账号的 `authorized_keys`，再撤回对应的 sudoers 文件。恢复前重新核对服务器指纹、腾讯专用公钥和工作区授权。身份不可用时腾讯端暂缓新提醒，账本用于原有回执的对账。
