// AnzoBot: shows "AnzoBot" instead of "Claude" on the tab group that the
// Claude in Chrome extension creates for ANZO's sessions.
//
// How the Claude extension names its groups (read from its own code, v1.0.97):
// it sets the fixed title "Claude" when it creates or re-creates a group, and
// afterwards only swaps a status prefix in front of whatever title the group
// has (⌛ working, 🔔 needs you, ✅ done) -- it tracks groups by id, never by
// name. So renaming the base name is safe and the prefixes keep working; this
// just has to catch every time the title becomes "Claude" again.
//
// Only groups named exactly "Claude" (with or without a status prefix) are
// touched: "Claude (MCP)" groups, which the Claude extension actively keeps
// named, and any group you named yourself are left alone.

const FROM = "Claude";
const TO = "AnzoBot";
const PREFIX = /^(⌛|🔔|✅)\s*/u;

async function rename(group) {
  if (!group || typeof group.title !== "string") return;
  const m = group.title.match(PREFIX);
  const prefix = m ? m[1] : "";
  const base = group.title.slice(m ? m[0].length : 0).trim();
  if (base !== FROM) return;
  try {
    // Same format the Claude extension uses: prefix glued to the name.
    await chrome.tabGroups.update(group.id, { title: prefix + TO });
  } catch (_) {
    // The group may have been closed in the meantime; nothing to do.
  }
}

async function renameAll() {
  try {
    for (const group of await chrome.tabGroups.query({})) await rename(group);
  } catch (_) {}
}

chrome.tabGroups.onCreated.addListener(rename);
chrome.tabGroups.onUpdated.addListener(rename);
chrome.runtime.onInstalled.addListener(renameAll);
chrome.runtime.onStartup.addListener(renameAll);
