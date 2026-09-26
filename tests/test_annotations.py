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

    def test_claim_blocks_editing_and_second_agent(self):
        self.store.claim(self.id, "doc", 1)
        revision = self.item["revision"]
        for operation in (
            lambda: self.store.edit(self.id, "doc", revision, "changed"),
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


class FakeDesign:
    """Fusion attributes follow geometry through recomputes; memory references may not."""

    def __init__(self):
        self.attributes = []
        self.timeline = SimpleNamespace(markerPosition=5, count=5)

    def findAttributes(self, group, name):
        return [a for a in self.attributes if a.groupName == group and (not name or a.name == name)]

    def entity(self, name, length=10.0):
        entity = SimpleNamespace(isValid=True, name=name, objectType="adsk::fusion::BRepEdge", length=length)
        design = self

        class Attributes:
            def add(self, group, attribute_name, value):
                attribute = SimpleNamespace(groupName=group, name=attribute_name, value=value,
                                            parent=entity, otherParents=[])
                attribute.deleteMe = lambda: design.attributes.remove(attribute)
                design.attributes.append(attribute)
                return attribute

        entity.attributes = Attributes()
        return entity


class BridgeTests(unittest.TestCase):
    def setUp(self):
        annotations.clear()
        self.design = FakeDesign()
        self.doc = SimpleNamespace(isValid=True, name="Design", products=SimpleNamespace(
            itemByProductType=lambda product: self.design))
        self.entity = self.design.entity("Edge A")
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
        with self.assertRaises(ValueError):
            self.ui("edit", id=item["id"], revision=2, text="Changed")
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

    def test_remove_working_row_keeps_client_references_until_finish(self):
        for action in ("complete", "release"):
            with self.subTest(action=action):
                self.selection.entities = [self.entity]
                item = self.create()
                claimed = self.tool(action="claim", id=item["id"], revision=1)
                ref = claimed["references"][0][1:]
                state = self.ui("delete", id=item["id"], revision=claimed["revision"])
                self.assertFalse(state["annotations"])
                self.assertFalse(self.tool(action="list")["annotations"])
                self.assertIs(value_builders.OBJECT_STORE[ref], self.entity)
                # Deletion is invisible to the client: no abort protocol or fields.
                self.assertEqual(annotations.STORE.items[item["id"]]["status"], "in_progress")
                finished = self.tool(action=action, id=item["id"],
                                     claim_token=claimed["claim_token"], result="Finished")
                self.assertEqual(finished["status"], "done" if action == "complete" else "failed")
                self.assertNotIn("dismissed", finished)
                self.assertNotIn("abort_requested", finished)
                self.assertFalse(annotations.state()["annotations"])
                self.assertNotIn(item["id"], annotations.STORE.items)
                self.assertNotIn(ref, value_builders.OBJECT_STORE)

    def test_removed_claim_still_requires_owner_token(self):
        item = self.create()
        claimed = self.tool(action="claim", id=item["id"], revision=1)
        self.ui("delete", id=item["id"], revision=claimed["revision"])
        response = annotations.manage_annotations(dict(action="complete", id=item["id"],
                                                      claim_token="wrong", result="Done"))
        self.assertTrue(response["isError"])
        self.assertIn(claimed["references"][0][1:], value_builders.OBJECT_STORE)
        self.doc.isValid = False
        self.app.activeDocument = None
        self.assertFalse(annotations.state()["annotations"])
        self.assertNotIn(item["id"], annotations.STORE.items)
        self.assertNotIn(claimed["references"][0][1:], value_builders.OBJECT_STORE)

    def test_context_menu_capture_is_handed_to_palette_once(self):
        annotations.capture_for_palette()
        self.selection.entities = []
        self.assertNotIn("pending_capture", self.tool(action="list"))
        pending = annotations.ui_action("list", {})["pending_capture"]
        self.assertEqual(pending["selections"][0]["name"], "Edge A")
        self.assertNotIn("pending_capture", annotations.ui_action("list", {}))
        state = self.ui("create", text="Round this", capture_id=pending["capture_id"])
        self.assertEqual(state["annotations"][0]["selections"][0]["name"], "Edge A")

    def test_context_menu_capture_stays_with_its_document(self):
        annotations.capture_for_palette()
        self.app.activeDocument = SimpleNamespace(isValid=True, name="Other")
        self.assertNotIn("pending_capture", annotations.ui_action("list", {}))
        self.app.activeDocument = self.doc
        self.assertIn("pending_capture", annotations.ui_action("list", {}))

    def test_context_menu_capture_requires_selection(self):
        self.selection.entities = []
        with self.assertRaises(ValueError):
            annotations.capture_for_palette()
        self.assertNotIn("pending_capture", annotations.ui_action("list", {}))

    def marker(self):
        [marker] = self.design.findAttributes(annotations.MARKER_GROUP, "")
        return marker

    def test_marker_follows_recomputed_geometry(self):
        item = self.create()
        self.assertEqual(self.marker().value, item["id"])
        # A parameter change invalidates the memory reference; the marker moves along.
        recomputed = self.design.entity("Edge A")
        self.entity.isValid = False
        self.marker().parent = recomputed
        self.assertEqual(annotations.state()["annotations"][0]["selections"][0]["status"], "ok")
        claimed = self.tool(action="claim", id=item["id"], revision=1)
        self.assertEqual(claimed["warnings"], [])
        self.assertIs(value_builders.OBJECT_STORE[claimed["references"][0][1:]], recomputed)

    def test_changed_geometry_is_claimable_with_warning(self):
        item = self.create()
        self.entity.length = 12.0
        self.assertEqual(annotations.state()["annotations"][0]["selections"][0]["status"], "changed")
        claimed = self.tool(action="claim", id=item["id"], revision=1)
        self.assertIn("changed since it was captured", claimed["warnings"][0])

    def test_split_geometry_references_every_piece(self):
        item = self.create()
        other = self.design.entity("Edge A", length=4.0)
        self.entity.length = 4.0
        self.marker().otherParents = [other]
        selection = annotations.state()["annotations"][0]["selections"][0]
        self.assertEqual((selection["status"], selection["parts"]), ("split", 2))
        claimed = self.tool(action="claim", id=item["id"], revision=1)
        self.assertEqual(len(claimed["references"]), 2)
        self.assertEqual(claimed["selections"][0]["references"], claimed["references"])
        self.assertIs(value_builders.OBJECT_STORE[claimed["references"][1][1:]], other)
        self.assertIn("was split", claimed["warnings"][0])
        self.ui("select", id=item["id"])
        self.assertEqual(self.selection.entities, [self.entity, other])

    def test_consumed_geometry_is_missing_and_cannot_be_claimed(self):
        item = self.create()
        self.marker().parent = None  # E.g. the edge disappeared into a fillet.
        self.assertEqual(annotations.state()["annotations"][0]["selections"][0]["status"], "missing")
        response = annotations.manage_annotations(dict(action="claim", id=item["id"], revision=1))
        self.assertTrue(response["isError"])

    def test_undone_marker_falls_back_to_memory_reference(self):
        self.create()
        self.design.attributes.clear()  # Ctrl+Z removed the marker.
        self.assertEqual(annotations.state()["annotations"][0]["selections"][0]["status"], "ok")

    def test_rolled_back_timeline_is_unverified(self):
        item = self.create()
        self.design.timeline.markerPosition = 2
        self.marker().parent = None
        self.assertEqual(annotations.state()["annotations"][0]["selections"][0]["status"], "unverified")
        claimed = self.tool(action="claim", id=item["id"], revision=1)
        self.assertIn("timeline is rolled back", claimed["warnings"][0])

    def test_markers_removed_on_delete_complete_and_stop_but_kept_on_release(self):
        item = self.create()
        self.ui("delete", id=item["id"], revision=1)
        self.assertFalse(self.design.attributes)
        self.selection.entities = [self.entity]
        item = self.create()
        claimed = self.tool(action="claim", id=item["id"], revision=1)
        self.tool(action="release", id=item["id"], claim_token=claimed["claim_token"], result="Failed")
        self.assertEqual(annotations.state()["marker_count"], 1)
        self.ui("edit", id=item["id"], revision=3, text="Retry")
        claimed = self.tool(action="claim", id=item["id"], revision=4)
        self.tool(action="complete", id=item["id"], claim_token=claimed["claim_token"], result="Done")
        self.assertFalse(self.design.attributes)
        self.assertIsNone(annotations.state()["annotations"][0]["selections"][0]["status"])
        self.selection.entities = [self.entity]
        self.create()
        annotations.clear()
        self.assertFalse(self.design.attributes)

    def test_reactivating_completed_work_marks_current_geometry(self):
        item = self.create()
        claimed = self.tool(action="claim", id=item["id"], revision=1)
        self.entity.length = 12.0  # The agent's change is the new baseline.
        self.tool(action="complete", id=item["id"], claim_token=claimed["claim_token"], result="Done")
        self.ui("edit", id=item["id"], revision=3, text="Longer still")
        self.assertEqual(self.marker().name, f"{item['id']}_0")
        self.assertEqual(annotations.state()["annotations"][0]["selections"][0]["status"], "ok")

    def test_recapture_moves_marker_to_new_selection(self):
        item = self.create()
        edge_b = self.design.entity("Edge B")
        self.selection.entities = [edge_b]
        capture = self.ui("capture")
        self.ui("edit", id=item["id"], revision=1, text="Other edge", capture_id=capture["capture_id"])
        self.assertIs(self.marker().parent, edge_b)

    def test_remove_markers_purges_leftovers_and_keeps_annotations(self):
        self.create()
        leftover = self.design.entity("Saved earlier")
        leftover.attributes.add(annotations.MARKER_GROUP, "old_0", "old")
        self.assertEqual(annotations.state()["marker_count"], 2)
        state = self.ui("remove_markers")
        self.assertEqual(state["marker_count"], 0)
        self.assertEqual(state["annotations"][0]["selections"][0]["status"], "ok")

    def test_clear_discards_annotations_and_drafts(self):
        capture = self.ui("capture")
        self.create()
        annotations.clear()
        self.assertFalse(annotations.state()["annotations"])
        with self.assertRaises(ValueError):
            self.ui("create", text="Lost draft", capture_id=capture["capture_id"])


if __name__ == "__main__":
    unittest.main()
