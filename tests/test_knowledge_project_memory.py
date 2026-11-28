import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from deployment.hindsight import knowledge_project_memory as memory


class MemoryCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tools, self.writes, self.docs = {}, [], {}
        self.scope = memory.Scope("issue", "project", "fanren-work")
        self.op = str(uuid4())
        memory.bind(self, lambda: self.scope, self.upstream)

    def tool(self, func):
        self.tools[func.__name__] = func
        return func

    async def upstream(self, tool, args, timeout):
        key = args.get("document_id")
        if tool == "recall":
            return {"results": []}, False
        if tool == "get_document":
            if key not in self.docs:
                return {"error": f"Document '{key}' not found"}, True
            return self.docs[key], False
        self.writes.append(args)
        self.docs[key] = dict(id=key, bank_id=args["bank_id"], original_text=args["content"],
                              tags=args["tags"], document_metadata=args["metadata"])
        return {"operation_id": args["operation_id"], "status": "accepted"}, False

    async def write(self, expected, text="sourced new fact", bank="fanren-work"):
        return await self.tools["retain"](bank, "same-document", expected, text, "source", self.op)

    async def test_current_project_requires_its_own_search(self):
        await self.tools["recall"]("multica-4-dot", "cross-bank sources")
        with self.assertRaises(ValueError):
            await self.write("new")
        await self.tools["recall"]("fanren-work", "same topic")
        with self.assertRaises(ValueError):
            await self.write("new", bank="multica-4-dot")
        self.assertEqual(self.writes, [])

    async def test_replay_and_update_preserve_document(self):
        await self.tools["recall"]("fanren-work", "same topic")
        await self.write("new", "original")
        self.assertEqual((await self.write("new", "original"))["status"], "already_covered")
        with self.assertRaises(ValueError):
            await self.write("new")
        with self.assertRaises(ValueError):
            await self.write("0" * 64)
        self.op = str(uuid4())
        result = await self.tools["get_document"]("fanren-work", "same-document")
        await self.write(result["original_sha256"])
        self.assertEqual((len(self.docs), len(self.writes)), (1, 2))
        self.assertEqual(self.writes[-1]["content"], "original\n\nsourced new fact")

    async def test_unknown_read_never_creates(self):
        await self.tools["recall"]("fanren-work", "same topic")
        self.docs["same-document"] = {"error": "upstream unavailable"}
        with self.assertRaises(ValueError):
            await self.write("new")
        self.assertEqual(self.writes, [])

class NativeScopeCase(unittest.TestCase):
    def test_custom_workdir_uses_native_issue_and_live_project(self):
        task, issue, project = (str(uuid4()) for _ in range(3))
        run = dict(id=task, issue_id=issue, agent_id=memory.ROLE, workspace_id=memory.WORKSPACE,
                   status="running", work_dir="D:/fanren-workspace")
        card = dict(id=issue, workspace_id=memory.WORKSPACE, project_id=project)
        env = dict(MULTICA_AGENT_ID=memory.ROLE, MULTICA_WORKSPACE_ID=memory.WORKSPACE,
                   MULTICA_TASK_ID=task, MULTICA_TOKEN="mat_fixture")
        with TemporaryDirectory() as directory, patch.object(memory.Path, "home", return_value=Path(directory)), \
                patch.dict(memory.os.environ, env, clear=True), patch.object(memory, "build_opener") as http:
            registry = Path(directory) / ".multica/integrations/hindsight/omp-project-banks.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(json.dumps({"multicaWorkspaces": {memory.WORKSPACE_DIR: {project: "fanren-work"}}}))
            def response(request, timeout):
                data = [run] if "/agents/" in request.full_url else card
                return io.BytesIO(json.dumps(data).encode())
            http.return_value.open.side_effect = response
            self.assertEqual(memory.current_scope(), memory.Scope(issue, project, "fanren-work"))
            card["project_id"] = str(uuid4())
            with self.assertRaisesRegex(ValueError, "no unique registered"):
                memory.current_scope()
            run["status"] = "completed"
            with self.assertRaisesRegex(ValueError, "not active"):
                memory.current_scope()
