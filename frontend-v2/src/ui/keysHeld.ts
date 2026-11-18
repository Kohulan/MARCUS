// The one check every page-level key handler makes before it acts: something above the tool
// owns the keys. That is a native <dialog> open (the structure editor, the COCONUT form), a
// modal div dialog (Compare, Keys: role="dialog" aria-modal="true"), or the tool hidden
// behind DesktopOnly's note (data-keys-off: a narrowed window must not decide unseen).

const HOLDERS = 'dialog[open], [role="dialog"][aria-modal="true"], [data-keys-off]';

/** True while a dialog or the hidden tool holds the keys. */
export function keysHeld(): boolean {
  return document.querySelector(HOLDERS) !== null;
}
