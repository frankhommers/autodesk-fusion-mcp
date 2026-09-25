"use strict";
const $ = id => document.getElementById(id);
let current = {document_id:null, annotations:[]};
let captureId = null, editing = null, busy = false, polling = false, generation = 0;
const labels = {open:"Open", in_progress:"In progress · Locked", done:"Completed", failed:"Interrupted / failed", aborted:"Aborted"};

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
    $("save").disabled ||= !!stale || !$("text").value.trim() || (!editing && !captureId);
    $("cancel").disabled = busy;
    $("notice").textContent = locked()
        ? "The agent is working on this annotation. Editing is locked."
        : stale ? "This annotation changed. Cancel or reopen Edit to load its current version." : "";
}
function applyState(next) {
    if (current.document_id !== next.document_id) resetEditor();
    const changed = JSON.stringify(current) !== JSON.stringify(next);
    current = next;
    document.documentElement.dataset.theme = next.theme || "light";
    $("document").textContent = next.document_name || "No document open";
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
        const abortPending = item.status === "in_progress" && item.abort_requested;
        card.append(node("span", abortPending ? "Abort requested · Locked" : labels[item.status], `badge ${item.status}`));
        if (abortPending) card.append(node("p", "Waiting for the agent to stop. Running operations may finish first.", "muted"));
        card.append(node("p", item.text, "note"));
        card.append(node("p", selectionLabel(item.selections), "muted"));
        if (item.selections.some(s => !s.valid)) card.append(node("p", "Selection is no longer valid. Edit this annotation to capture it again.", "muted"));
        if (item.result) card.append(node("p", item.result, "result"));
        const actions = node("div", undefined, "row");
        function button(label, handler, disabled = false) {
            const b = node("button", label); b.type = "button";
            b.disabled = busy || disabled; b.onclick = handler; actions.append(b);
            return b;
        }
        button("Show selection", () => act(async () => applyState(await request("select", {id:item.id, document_id:current.document_id}))));
        if (item.status === "in_progress") {
            const abort = button(abortPending ? "Abort requested" : "Abort", () => act(async () => {
                applyState(await request("abort", {id:item.id, revision:item.revision, document_id:current.document_id}));
            }), !!item.abort_requested);
            abort.title = "Ask the agent to stop. Existing changes are not undone.";
        }
        button(item.status === "open" ? "Edit" : "Edit / Reactivate", () => edit(item), item.status === "in_progress");
        const remove = button("Delete", () => act(async () => {
            applyState(await request("delete", {id:item.id, revision:item.revision, document_id:current.document_id}));
            if (editing?.id === item.id) resetEditor();
        }), item.status === "in_progress");
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
async function poll() {
    if (busy || polling || !window.adsk) return;
    polling = true;
    const requestedGeneration = generation;
    try {
        const next = await request("list");
        if (!busy && generation === requestedGeneration) applyState(next);
    } catch (error) { $("error").textContent = error.message; }
    finally { polling = false; }
}
controls(); poll(); setInterval(poll, 1500);
