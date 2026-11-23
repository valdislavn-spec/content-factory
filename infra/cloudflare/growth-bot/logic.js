/** Pure helpers for the GrowthBot (no Workers APIs, easy to test). */

export const LANGS = ["en", "es", "ru"];

export function detectLang(code) {
  const prefix = String(code || "").toLowerCase().split("-")[0];
  return LANGS.includes(prefix) ? prefix : "en";
}

/** "/start ref_123" -> "123" */
export function parseRefPayload(text) {
  const match = /^\/start(?:\s+ref_(\d{3,}))?\s*$/.exec(String(text || "").trim());
  return match && match[1] ? match[1] : null;
}

/** Telegram getChatMember result -> boolean. */
export function isSubscribed(member) {
  if (!member || typeof member !== "object") return false;
  const status = member.status;
  if (status === "creator" || status === "administrator" || status === "member") return true;
  return status === "restricted" && member.is_member === true;
}

export function pickWinner(participants, randomFn = Math.random) {
  if (!Array.isArray(participants) || participants.length === 0) return null;
  const index = Math.floor(randomFn() * participants.length);
  return participants[Math.min(index, participants.length - 1)];
}

export function dedupeAppend(list, value) {
  const values = Array.isArray(list) ? list : [];
  return values.includes(value) ? values : values.concat([value]);
}

export function referralLink(botUsername, userId) {
  return "https://t.me/" + String(botUsername || "").replace(/^@/, "") + "?start=ref_" + userId;
}

export function formatUserLabel(user) {
  if (!user) return "—";
  if (user.username) return "@" + user.username;
  return String(user.id || "—");
}
