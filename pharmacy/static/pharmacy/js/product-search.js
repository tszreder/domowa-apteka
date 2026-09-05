// Product search shared by the add screen and the check screen.
//
// Extracted from autocomplete.js when the check screen needed the same picker:
// two copies of a debounce, an abort controller and a sequence guard is how two
// screens end up disagreeing about what "search" does. Everything here is
// screen-agnostic; anything that touches a form field or navigates stays in the
// screen's own script.
//
// Loaded before those scripts in document order. Both carry `defer`, and the
// HTML spec runs deferred scripts in document order, so tag order in the
// template is the whole mechanism — which is why a template test asserts it.
(() => {
  'use strict';

  const DEBOUNCE_MS = 200;
  const MIN_QUERY_LENGTH = 2;
  const SUGGESTIONS_URL = '/suggestions/';

  function clearList(list) {
    while (list.firstChild) list.removeChild(list.firstChild);
    list.hidden = true;
  }

  function makeOption(label, onPick) {
    const li = document.createElement('li');
    li.setAttribute('role', 'option');
    li.tabIndex = -1;
    li.textContent = label; // textContent, never innerHTML: registry names are publisher data.
    li.addEventListener('mousedown', (event) => {
      // mousedown, not click: fires before the input's blur hides the list.
      event.preventDefault();
      onPick();
    });
    return li;
  }

  function renderList(list, options) {
    clearList(list);
    if (options.length === 0) return;
    options.forEach((option) => list.appendChild(option));
    list.hidden = false;
  }

  // Only `makeOption` rows carry role="option"; a failure message rendered
  // into the same list is deliberately excluded, so arrow keys cannot land
  // on a row that does nothing when picked.
  function optionsOf(list) {
    return Array.from(list.querySelectorAll('[role="option"]'));
  }

  function activateOption(list, index) {
    const options = optionsOf(list);
    options.forEach((el, i) => el.classList.toggle('active', i === index));
    if (options[index]) options[index].scrollIntoView({ block: 'nearest' });
  }

  function attachKeyboardNav(input, list, onPickIndex) {
    let activeIndex = -1;
    input.addEventListener('keydown', (event) => {
      const options = optionsOf(list);
      if (list.hidden || options.length === 0) return;
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        activeIndex = (activeIndex + 1) % options.length;
        activateOption(list, activeIndex);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        activeIndex = (activeIndex - 1 + options.length) % options.length;
        activateOption(list, activeIndex);
      } else if (event.key === 'Enter') {
        if (activeIndex >= 0) {
          event.preventDefault();
          onPickIndex(activeIndex);
          activeIndex = -1;
        }
      } else if (event.key === 'Escape') {
        clearList(list);
        activeIndex = -1;
      }
    });
    input.addEventListener('input', () => {
      activeIndex = -1;
    });
  }

  // A lookup failure must never be silent (PRD guardrail). Picking a
  // suggestion is the only way to add an item in v1, so a dead endpoint
  // otherwise looks identical to "this drug is not in the registry".
  function renderMessage(list, text) {
    clearList(list);
    const li = document.createElement('li');
    li.textContent = text;
    li.className = 'suggestion-message';
    li.setAttribute('aria-live', 'polite');
    list.appendChild(li);
    list.hidden = false;
  }

  function presentationLabel(presentation) {
    return [presentation.name, presentation.strength, presentation.form]
      .filter(Boolean)
      .join(' — ');
  }

  // Wires `input` to `/suggestions/` and renders picks into `list`. Every piece
  // of per-search state lives in this closure, so two calls on one page would
  // not share a debounce timer or a sequence counter.
  //
  // `onInput` runs on every keystroke before the debounce: the add screen uses
  // it to clear its hidden fields, so a stale product id can never be submitted
  // alongside an edited name. The check screen has nothing to clear and omits it.
  function attachPresentationSearch({ input, list, onPick, onInput }) {
    let sequence = 0;
    let latestRenderedSequence = 0;
    let debounceTimer = null;
    let abortController = null;

    function renderPresentationOptions(presentations) {
      const options = presentations.map((presentation) =>
        makeOption(presentationLabel(presentation), () => onPick(presentation))
      );
      renderList(list, options);
    }

    async function fetchSuggestions(query) {
      const mySequence = ++sequence;
      if (abortController) abortController.abort();
      abortController = new AbortController();
      try {
        const response = await fetch(
          `${SUGGESTIONS_URL}?q=${encodeURIComponent(query)}`,
          { signal: abortController.signal }
        );
        // Check before parsing: an expired session redirects to the login
        // page, `fetch` follows it, and `response.json()` would throw a
        // SyntaxError on HTML that the catch below would re-throw as an
        // unhandled rejection — leaving the user typing into a dead field.
        if (!response.ok) {
          if (mySequence < latestRenderedSequence) return;
          latestRenderedSequence = mySequence;
          renderMessage(
            list,
            'Nie udało się pobrać podpowiedzi. Zaloguj się ponownie i spróbuj jeszcze raz.'
          );
          return;
        }
        const data = await response.json();
        // A slower, superseded response must never overwrite a newer one.
        if (mySequence < latestRenderedSequence) return;
        latestRenderedSequence = mySequence;
        renderPresentationOptions(data.results);
      } catch (error) {
        if (error.name === 'AbortError') return;
        if (mySequence < latestRenderedSequence) return;
        latestRenderedSequence = mySequence;
        renderMessage(
          list,
          'Nie udało się pobrać podpowiedzi. Sprawdź połączenie i spróbuj jeszcze raz.'
        );
      }
    }

    input.addEventListener('input', () => {
      if (onInput) onInput();
      if (debounceTimer) clearTimeout(debounceTimer);
      const query = input.value.trim();
      if (query.length < MIN_QUERY_LENGTH) {
        clearList(list);
        return;
      }
      debounceTimer = setTimeout(() => fetchSuggestions(query), DEBOUNCE_MS);
    });

    attachKeyboardNav(input, list, (index) => {
      const li = optionsOf(list)[index];
      if (li) li.dispatchEvent(new MouseEvent('mousedown'));
    });
  }

  window.ProductSearch = {
    clearList,
    makeOption,
    renderList,
    optionsOf,
    activateOption,
    attachKeyboardNav,
    renderMessage,
    presentationLabel,
    attachPresentationSearch,
  };
})();
