import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from deployment.hindsight import squad_index as si


class LeaderUpdates(IsolatedAsyncioTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.ledger = Path(directory.name) / "ledger"
        self.original = "previous evidence"
        self.note = "note"
        self.row = {"id": self.note, "issue_id": "card", "source_task_id": "run", "author_type": "agent",
                    "author_id": "dev-lead", "content": si.PREFIX + "dev\n" + json.dumps(
                        dict(base_sha256=si.digest(self.original), commit="a"*40, addition="new evidence"))}
        self.doc = dict(bank_id=si.BANK, id=si.ROUTES["dev"][1], original_text=self.original, tags=["existing"],
                        document_metadata={"original": "kept"}, retain_params={"context": "source context"})
        self.writes = []
        self.reply_lost = False
        self.run_state = "running"

    def get(self, path):
        if path.startswith("squads/"):
            team = "dev" if path.endswith(si.ROUTES["dev"][0]) else "qa"
            return dict(id=si.ROUTES[team][0], leader_id=team+"-lead", workspace_id=si.WORKSPACE)
        if path.endswith("/comments"):
            return [self.row]
        if "/task-runs?" in path:
            return [dict(id="run", agent_id="dev-lead", issue_id="card", workspace_id=si.WORKSPACE, status=self.run_state)]
        return dict(id="card", project_id="business", workspace_id=si.WORKSPACE)

    async def upstream(self, tool, args, timeout):
        if tool == "get_document":
            return self.doc, False
        if tool == "retain":
            self.writes.append(args)
            self.doc.update(original_text=args["content"], document_metadata=args["metadata"])
            if self.reply_lost:
                raise TimeoutError("lost response")
            return {"operation_id": args["operation_id"]}, False
        return {"operation_id": args["operation_id"], "status": "completed"}, False

    def apply(self, team="dev", agent="dev-lead"):
        return si.maintain(team, "card", self.note, agent, "run", self.get, self.upstream, self.ledger)

    async def test_current_appointment_and_note_scope(self):
        for team, agent in [("qa", "dev-lead"), ("dev", "old-lead")]:
            with self.assertRaises(ValueError):
                await self.apply(team, agent)
        for field, bad in [("issue_id","other"), ("author_id","other"), ("source_task_id","other"),
                           ("author_type","user"), ("content",self.row["content"].replace("v1 dev","v1 qa")),
                           ("content",self.row["content"].replace('"commit":','"bank_id":"other","commit":'))]:
            with self.subTest(field=field):
                saved=self.row[field]
                self.row[field]=bad
                with self.assertRaises(ValueError):
                    await self.apply()
                self.row[field]=saved
        self.run_state = "completed"
        with self.assertRaises(ValueError):
            await self.apply()
        self.assertEqual(self.writes, [])

    async def test_stale_candidate_and_wrong_document(self):
        self.doc["original_text"] = "changed concurrently"
        with self.assertRaises(ValueError):
            await self.apply()
        self.doc["id"] = "not-the-canonical-id"
        with self.assertRaises(ValueError):
            await self.apply()
        self.assertEqual(self.writes, [])

    async def test_update_and_replay(self):
        self.assertEqual((await self.apply())["status"], "completed")
        self.assertEqual((await self.apply())["status"], "already_covered")
        self.assertEqual(len(self.writes), 1)
        w = self.writes[0]
        self.assertEqual((w["bank_id"],w["document_id"],w["content"]),
                         (si.BANK,si.ROUTES["dev"][1],self.original+"\n\nnew evidence"))
        self.assertEqual((w["tags"], w["metadata"]["original"], w["context"]), (["existing"], "kept","source context"))

    async def test_unknown_submission_reconciles_before_any_new_write(self):
        self.reply_lost = True
        with self.assertRaises(TimeoutError):
            await self.apply()
        self.assertEqual((await self.apply())["status"], "already_covered")
        self.assertEqual(len(self.writes), 1)
