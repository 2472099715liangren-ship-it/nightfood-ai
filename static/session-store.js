/* Short-lived browser history. Store IDs and preferences; reload merchant facts from the API. */
const storageKey = "nightfind-conversation-v1";
const maxAge = 24 * 60 * 60 * 1000;

export function loadConversation() {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey));
    if (
      !value ||
      value.version !== 1 ||
      !Number.isFinite(value.savedAt) ||
      Date.now() - value.savedAt > maxAge
    )
      return null;
    return value;
  } catch {
    return null;
  }
}

export function saveConversation(state) {
  try {
    localStorage.setItem(
      storageKey,
      JSON.stringify({
        version: 1,
        savedAt: Date.now(),
        history: state.history.slice(-30),
        preferences: state.preferences,
        stage: state.result?.stage,
        lookupMessage: state.lookupMessage,
        selectedId: state.selected?.id,
        comparedIds: [...state.compared.keys()],
        lastRequest: state.lastRequest,
        failedRequest: state.failedRequest || state.busy,
        draft: state.draft,
        keyword: state.keyword,
        district: state.district,
      }),
    );
  } catch {
    /* Private browsing or full storage must not block dining decisions. */
  }
}

export function clearConversation() {
  try {
    localStorage.removeItem(storageKey);
  } catch {
    /* Storage may be unavailable. */
  }
}
