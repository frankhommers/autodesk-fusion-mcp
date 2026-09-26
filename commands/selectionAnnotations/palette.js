"use strict";
const $ = id => document.getElementById(id);
let current = {document_id:null, annotations:[]};
let captureId = null, editing = null, busy = false, polling = false, generation = 0;
const labels = {open:"Open", in_progress:"In progress · Locked", done:"Completed", failed:"Interrupted / failed"};
const selectionNotes = {
    changed:"changed since it was captured",
    split:"was split into several pieces",
    missing:"is no longer in the design. Edit this annotation to capture it again",
    unverified:"cannot be checked while the timeline is rolled back",
};

async function request(action, data = {}) {
    const raw = await window.adsk.fusionSendData(action, JSON.stringify(data));
    const response = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!response.ok) throw new Error(response.error);
    return response.data;
}
function selectionLabel(selections) {
    return selections.map(s => s.name || (s.objectType || "Object").split("::").pop()).join(", ");
}
function node(tag, text, cls) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (cls) el.className = cls;
    return el;
}
function resetEditor() {
    editing = null; captureId = null;
    $("text").value = "";
    $("editor-title").textContent = "New annotation";
    $("selection").textContent = "Select objects in Fusion, then capture the selection.";
    $("save").textContent = "Add";
    $("cancel").hidden = true;
}
function locked() {
    return editing && (current.annotations.find(a => a.id === editing.id)?.status === "in_progress");
}
function controls() {
    const item = editing && current.annotations.find(a => a.id === editing.id);
    const stale = editing && (!item || item.revision !== editing.revision);
    const disabled = busy || !current.document_id || !!locked();
    for (const id of ["text", "capture", "save"]) $(id).disabled = disabled;
    $("markers").disabled = busy || !current.document_id;
    $("save").disabled ||= !!stale || !$("text").value.trim() || (!editing && !captureId);
    $("cancel").disabled = busy;
    $("notice").textContent = locked()
        ? "The agent is working on this annotation. Editing is locked."
        : stale ? "This annotation changed. Cancel or reopen Edit to load its current version." : "";
}
// A capture from the right-click menu starts a new annotation.
function takeCapture(next) {
    const pending = next.pending_capture;
    if (!pending) return;
    if (editing && !window.confirm("Discard the current edit?")) return;
    if (editing) resetEditor();
    captureId = pending.capture_id;
    $("selection").textContent = selectionLabel(pending.selections);
    $("text").focus();
}
function applyState(next) {
    if (current.document_id !== next.document_id) resetEditor();
    takeCapture(next);
    const changed = JSON.stringify(current) !== JSON.stringify(next);
    current = next;
    document.documentElement.dataset.theme = next.theme || "light";
    $("document").textContent = next.document_name || "No document open";
    $("markers").hidden = !next.marker_count;
    $("markers").textContent = `Remove markers from design (${next.marker_count})`;
    if (changed) render();
    controls();
}
async function act(fn) {
    if (busy) return;
    generation++;
    busy = true; $("error").textContent = ""; controls(); render();
    try { await fn(); }
    catch (error) { $("error").textContent = error.message; }
    finally { busy = false; controls(); render(); }
}
function edit(item) {
    if (editing && !window.confirm("Discard the current edit?")) return;
    editing = {id:item.id, revision:item.revision}; captureId = null;
    $("text").value = item.text;
    $("editor-title").textContent = "Edit annotation";
    $("selection").textContent = selectionLabel(item.selections);
    $("save").textContent = item.status === "open" ? "Save" : "Save and reactivate";
    $("cancel").hidden = false; controls(); $("text").focus();
}
function render() {
    const root = $("items"); root.replaceChildren();
    if (!current.annotations.length) root.append(node("p", "No annotations in this document.", "muted"));
    for (const item of current.annotations) {
        const card = node("article");
        card.append(node("span", labels[item.status], `badge ${item.status}`));
        card.append(node("p", item.text, "note"));
        card.append(node("p", selectionLabel(item.selections), "muted"));
        for (const s of item.selections) {
            if (selectionNotes[s.status]) card.append(node("p", `${selectionLabel([s])} ${selectionNotes[s.status]}.`, `warning ${s.status}`));
        }
        if (item.result) card.append(node("p", item.result, "result"));
        const actions = node("div", undefined, "row");
        function button(label, handler, disabled = false) {
            const b = node("button", label); b.type = "button";
            b.disabled = busy || disabled; b.onclick = handler; actions.append(b);
            return b;
        }
        button("Show selection", () => act(async () => applyState(await request("select", {id:item.id, document_id:current.document_id}))));
        button(item.status === "open" ? "Edit" : "Edit / Reactivate", () => edit(item), item.status === "in_progress");
        const remove = button("Delete", () => act(async () => {
            applyState(await request("delete", {id:item.id, revision:item.revision, document_id:current.document_id}));
            if (editing?.id === item.id) resetEditor();
        }));
        remove.className = "icon";
        remove.title = "Delete annotation";
        remove.setAttribute("aria-label", "Delete annotation");
        remove.replaceChildren();
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 16 16");
        svg.setAttribute("width", "14"); svg.setAttribute("height", "14");
        svg.setAttribute("aria-hidden", "true");
        const path = document.createElementNS(svg.namespaceURI, "path");
        path.setAttribute("d", "M2 4h12M6 4V2h4v2M4 4l1 10h6l1-10M6.5 6v6M9.5 6v6");
        path.setAttribute("fill", "none"); path.setAttribute("stroke", "currentColor");
        path.setAttribute("stroke-width", "1.2");
        svg.append(path); remove.append(svg);
        card.append(actions); root.append(card);
    }
}
$("capture").onclick = () => act(async () => {
    const result = await request("capture", {document_id:current.document_id});
    captureId = result.capture_id;
    $("selection").textContent = selectionLabel(result.selections);
});
$("save").onclick = () => act(async () => {
    const next = await request(editing ? "edit" : "create", {
        ...editing, document_id:current.document_id, text:$("text").value, capture_id:captureId
    });
    resetEditor(); applyState(next);
});
$("cancel").onclick = () => { resetEditor(); controls(); };
$("text").oninput = controls;
$("refresh").onclick = () => act(async () => applyState(await request("list")));
$("markers").onclick = () => {
    if (!window.confirm("Remove all Autodesk Fusion MCP markers from this design? Annotations stay, but can no longer follow geometry changes.")) return;
    act(async () => applyState(await request("remove_markers", {document_id:current.document_id})));
};
async function poll() {
    if (busy || polling || !window.adsk) return;
    polling = true;
    const requestedGeneration = generation;
    try {
        const next = await request("list");
        if (!busy && generation === requestedGeneration) applyState(next);
        else takeCapture(next);
    } catch (error) { $("error").textContent = error.message; }
    finally { polling = false; }
}
window.fusionJavaScriptHandler = {handle(action) {
    if (action === "refresh") poll();
    return "OK";
}};
controls(); poll(); setInterval(poll, 1500);
