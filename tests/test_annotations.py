"""State transitions, races and document isolation for selection annotations."""

import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import _fusion_test_bootstrap  # noqa: F401
from fusion_bridge.annotation_store import AnnotationStore
from fusion_bridge import annotations, value_builders


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = AnnotationStore()
        self.item = self.store.create("doc", "Round these edges", [object()])
        self.id = self.item["id"]

    def test_claim_blocks_all_user_mutations_and_second_agent(self):
        self.store.claim(self.id, "doc", 1)
        revision = self.item["revision"]
        for operation in (
            lambda: self.store.edit(self.id, "doc", revision, "changed"),
            lambda: self.store.delete(self.id, "doc", revision),
            lambda: self.store.claim(self.id, "doc", revision),
        ):
            with self.assertRaises(ValueError):
                operation()
        self.assertEqual(self.item["text"], "Round these edges")
        self.assertEqual(self.item["status"], "in_progress")

    def test_completion_keeps_result_then_edit_reactivates(self):
        self.store.claim(self.id, "doc", 1)
        token = self.item["claim_token"]
        self.store.finish(self.id, "doc", token, "Rounded with 2 mm radius")
        self.assertEqual(self.item["status"], "done")
        self.assertEqual(self.item["result"], "Rounded with 2 mm radius")
        self.store.edit(self.id, "doc", 3, "Use 3 mm instead")
        self.assertEqual(self.item["status"], "open")
        self.assertEqual(self.item["result"], "")
        self.store.claim(self.id, "doc", 4)
        with self.assertRaises(ValueError):
            self.store.finish(self.id, "doc", token, "Old completion")

    def test_stale_ui_cannot_overwrite_or_delete(self):
        self.store.edit(self.id, "doc", 1, "Changed")
        for op in (
            lambda: self.store.edit(self.id, "doc", 1, "Stale"),
            lambda: self.store.delete(self.id, "doc", 1),
            lambda: self.store.claim(self.id, "doc", 1),
        ):
            with self.assertRaises(ValueError):
                op()

    def test_release_unlocks_for_review_without_automatic_retry(self):
        self.store.claim(self.id, "doc", 1)
        self.store.finish(self.id, "doc", self.item["claim_token"], "Cancelled", failed=True)
        self.assertEqual(self.item["status"], "failed")
        self.store.delete(self.id, "doc", self.item["revision"])
        self.assertFalse(self.store.items)

    def test_wrong_document_or_token_cannot_finish(self):
        self.store.claim(self.id, "doc", 1)
        for doc, token in (("other", self.item["claim_token"]), ("doc", "wrong"), ("doc", None)):
            with self.assertRaises(ValueError):
                self.store.finish(self.id, doc, token, "Done")
        self.assertEqual(self.item["status"], "in_progress")

    def test_invalid_edit_is_atomic(self):
        before = dict(self.item)
        with self.assertRaises(ValueError):
            self.store.edit(self.id, "doc", 1, "  ")
        with self.assertRaises(ValueError):
            self.store.edit(self.id, "doc", 1, "Good text", [])
        self.assertEqual(self.item, before)


class Selections:
    def __init__(self, entities):
        self.entities = entities

    @property
    def count(self):
        return len(self.entities)

    def item(self, index):
        return SimpleNamespace(entity=self.entities[index])

    def clear(self):
        self.entities.clear()

    def add(self, entity):
        self.entities.append(entity)
        return True


class BridgeTests(unittest.TestCase):
    def setUp(self):
        annotations.clear()
        self.doc = SimpleNamespace(isValid=True, name="Design")
        self.entity = SimpleNamespace(isValid=True, name="Edge A", objectType="adsk::fusion::BRepEdge")
        self.selection = Selections([self.entity])
        self.app = SimpleNamespace(activeDocument=self.doc,
                                   userInterface=SimpleNamespace(activeSelections=self.selection))
        self.patch = patch.object(annotations, "get_app", return_value=self.app)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(annotations.clear)
        self.document = annotations.state()["document_id"]

    def ui(self, action, **kwargs):
        return annotations.ui_action(action, dict(document_id=self.document, **kwargs))

    def create(self):
        capture = self.ui("capture")
        self.selection.entities = []
        state = self.ui("create", text="Round this", capture_id=capture["capture_id"])
        return state["annotations"][0]

    def tool(self, **kwargs):
        response = annotations.manage_annotations(kwargs)
        self.assertFalse(response["isError"], response)
        return json.loads(response["content"][0]["text"])

    def test_capture_survives_deselection_and_read_does_not_claim(self):
        item = self.create()
        self.assertEqual(item["selections"][0]["name"], "Edge A")
        listed = self.tool(action="list")["annotations"][0]
        self.assertEqual(listed["status"], "open")
        self.assertNotIn("claim_token", listed)
        self.ui("select", id=item["id"])
        self.assertIs(self.selection.entities[0], self.entity)

    def test_claim_references_and_ui_lock_and_completion(self):
        item = self.create()
        claimed = self.tool(action="claim", id=item["id"], revision=1)
        ref = claimed["references"][0][1:]
        self.assertIs(value_builders.OBJECT_STORE[ref], self.entity)
        for action, extra in (("delete", {}), ("edit", {"text": "Changed"})):
            with self.assertRaises(ValueError):
                self.ui(action, id=item["id"], revision=2, **extra)
        listed = self.tool(action="list")["annotations"][0]
        self.assertNotIn("claim_token", listed)
        completed = self.tool(action="complete", id=item["id"], claim_token=claimed["claim_token"], result="Done")
        self.assertEqual(completed["status"], "done")
        self.assertNotIn(ref, value_builders.OBJECT_STORE)
        updated = self.ui("edit", id=item["id"], revision=3, text="Again")
        self.assertEqual(updated["annotations"][0]["status"], "open")

    def test_document_switch_and_close(self):
        item = self.create()
        claimed = self.tool(action="claim", id=item["id"], revision=1)
        self.app.activeDocument = SimpleNamespace(isValid=True, name="Other")
        self.assertEqual(annotations.state()["annotations"], [])
        with self.assertRaises(ValueError):
            self.ui("delete", id=item["id"], revision=2)
        response = annotations.manage_annotations(dict(action="complete", id=item["id"],
                                                      claim_token=claimed["claim_token"], result="Done"))
        self.assertTrue(response["isError"])
        self.doc.isValid = False
        annotations.state()
        self.assertFalse(annotations.STORE.items)
        self.assertNotIn(claimed["references"][0][1:], value_builders.OBJECT_STORE)

    def test_invalid_geometry_cannot_be_claimed(self):
        item = self.create()
        self.entity.isValid = False
        response = annotations.manage_annotations(dict(action="claim", id=item["id"], revision=1))
        self.assertTrue(response["isError"])
        self.assertEqual(annotations.state()["annotations"][0]["status"], "open")

    def test_failed_processing_is_visible_and_editable(self):
        item = self.create()
        claimed = self.tool(action="claim", id=item["id"], revision=1)
        released = self.tool(action="release", id=item["id"], claim_token=claimed["claim_token"], result="Could not round")
        self.assertEqual(released["status"], "failed")
        self.ui("delete", id=item["id"], revision=3)
        self.assertFalse(annotations.state()["annotations"])

    def test_abort_waits_for_owner_release_and_preserves_references(self):
        item = self.create()
        claimed = self.tool(action="claim", id=item["id"], revision=1)
        state = self.ui("abort", id=item["id"], revision=claimed["revision"])
        pending = state["annotations"][0]
        self.assertEqual(pending["status"], "in_progress")
        self.assertTrue(pending["abort_requested"])
        self.assertIn(claimed["references"][0][1:], value_builders.OBJECT_STORE)
        for action, extra in (("delete", {}), ("edit", {"text": "Changed"})):
            with self.assertRaises(ValueError):
                self.ui(action, id=item["id"], revision=pending["revision"], **extra)
        checked = self.tool(action="check", id=item["id"], claim_token=claimed["claim_token"])
        self.assertTrue(checked["abort_requested"])
        for action, token in (("complete", claimed["claim_token"]), ("release", "wrong")):
            response = annotations.manage_annotations(dict(action=action, id=item["id"],
                                                          claim_token=token, result="Stopped"))
            self.assertTrue(response["isError"])
        released = self.tool(action="release", id=item["id"], claim_token=claimed["claim_token"],
                             result="Stopped after first edge; changes retained")
        self.assertEqual(released["status"], "aborted")
        self.assertNotIn(claimed["references"][0][1:], value_builders.OBJECT_STORE)
        updated = self.ui("edit", id=item["id"], revision=released["revision"], text="Try again")
        self.assertFalse(updated["annotations"][0]["abort_requested"])
        self.assertEqual(updated["annotations"][0]["status"], "open")

    def test_abort_rejects_open_completed_and_stale_claim(self):
        item = self.create()
        with self.assertRaises(ValueError):
            self.ui("abort", id=item["id"], revision=1)
        claimed = self.tool(action="claim", id=item["id"], revision=1)
        with self.assertRaises(ValueError):
            self.ui("abort", id=item["id"], revision=1)
        done = self.tool(action="complete", id=item["id"], claim_token=claimed["claim_token"], result="Done")
        with self.assertRaises(ValueError):
            self.ui("abort", id=item["id"], revision=done["revision"])
        self.ui("edit", id=item["id"], revision=done["revision"], text="Again")
        second = self.tool(action="claim", id=item["id"], revision=4)
        with self.assertRaises(ValueError):
            self.ui("abort", id=item["id"], revision=claimed["revision"])
        checked = self.tool(action="check", id=item["id"], claim_token=second["claim_token"])
        self.assertFalse(checked["abort_requested"])
        response = annotations.manage_annotations(dict(action="check", id=item["id"],
                                                      claim_token=claimed["claim_token"]))
        self.assertTrue(response["isError"])

    def test_clear_discards_annotations_and_drafts(self):
        capture = self.ui("capture")
        self.create()
        annotations.clear()
        self.assertFalse(annotations.state()["annotations"])
        with self.assertRaises(ValueError):
            self.ui("create", text="Lost draft", capture_id=capture["capture_id"])


if __name__ == "__main__":
    unittest.main()
