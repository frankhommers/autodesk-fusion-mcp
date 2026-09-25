"""Session-only annotation state. Called exclusively on Fusion's main thread."""

from uuid import uuid4


class AnnotationStore:
    def __init__(self):
        self.items = {}

    def clear(self):
        self.items.clear()

    @staticmethod
    def text(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Enter an annotation first.")
        if len(value) > 10000:
            raise ValueError("Annotation text must be at most 10,000 characters.")
        return value.strip()

    def create(self, document, text, entities):
        text = self.text(text)
        if not entities:
            raise ValueError("Capture at least one selected object.")
        item = dict(id=uuid4().hex, document=document, text=text,
                    entities=list(entities), status="open", revision=1,
                    result="", claim_token=None, abort_requested=False)
        self.items[item["id"]] = item
        return item

    def get(self, item_id, document):
        item = self.items.get(item_id)
        if item is None or item["document"] != document:
            raise ValueError("Annotation is unavailable in the active document.")
        return item

    @staticmethod
    def check_revision(item, revision):
        if type(revision) is not int or revision != item["revision"]:
            raise ValueError("Annotation changed. Refresh before trying again.")

    def editable(self, item_id, document, revision):
        item = self.get(item_id, document)
        if item["status"] == "in_progress":
            raise ValueError("The agent is working on this annotation; it is locked.")
        self.check_revision(item, revision)
        return item

    def edit(self, item_id, document, revision, text, entities=None):
        item = self.editable(item_id, document, revision)
        text = self.text(text)
        if entities is not None and not entities:
            raise ValueError("Capture at least one selected object.")
        item.update(text=text, status="open", result="", abort_requested=False, revision=item["revision"] + 1)
        if entities is not None:
            item["entities"] = list(entities)
        return item

    def delete(self, item_id, document, revision):
        self.editable(item_id, document, revision)
        del self.items[item_id]

    def claim(self, item_id, document, revision):
        item = self.get(item_id, document)
        self.check_revision(item, revision)
        if item["status"] != "open":
            raise ValueError("Only open annotations can be claimed.")
        item.update(status="in_progress", claim_token=uuid4().hex,
                    revision=item["revision"] + 1)
        return item

    def request_abort(self, item_id, document, revision):
        item = self.get(item_id, document)
        self.check_revision(item, revision)
        if item["status"] != "in_progress":
            raise ValueError("Only in-progress annotations can be aborted.")
        if not item["abort_requested"]:
            item.update(abort_requested=True, revision=item["revision"] + 1)
        return item

    def check_claim(self, item_id, document, token):
        item = self.get(item_id, document)
        if item["status"] != "in_progress" or not token or token != item["claim_token"]:
            raise ValueError("A current claim token is required for this annotation.")
        return item

    def finish(self, item_id, document, token, result, failed=False):
        item = self.check_claim(item_id, document, token)
        if item["abort_requested"] and not failed:
            raise ValueError("Abort requested. Stop work and release the claim with a summary of partial changes.")
        result = self.text(result)
        status = "aborted" if item["abort_requested"] else "failed" if failed else "done"
        item.update(status=status, result=result,
                    claim_token=None, revision=item["revision"] + 1)
        return item
