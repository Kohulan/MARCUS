// The one check the review keys make before they act: something above the tool owns the
// keys. That is a native <dialog> open (every dialog: Modal in ui/modal), or the tool hidden
// behind DesktopOnly's note (data-keys-off: a narrowed window must not decide unseen).

const HOLDERS = "dialog[open], [data-keys-off]";

/** True while a dialog or the hidden tool holds the keys. */
export function keysHeld(): boolean {
  return document.querySelector(HOLDERS) !== null;
}
