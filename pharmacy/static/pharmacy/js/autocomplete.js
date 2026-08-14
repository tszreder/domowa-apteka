(() => {
  'use strict';

  const DEBOUNCE_MS = 200;

  const searchInput = document.getElementById('product-search');
  if (!searchInput) return;

  const suggestionsList = document.getElementById('suggestions');
  const productField = document.getElementById('id_product');
  const producerConfirmedField = document.getElementById('id_producer_confirmed');
  const producerField = document.getElementById('producer-field');
  const producerSearchInput = document.getElementById('producer-search');
  const producerSuggestionsList = document.getElementById('producer-suggestions');

  let sequence = 0;
  let latestRenderedSequence = 0;
  let debounceTimer = null;
  let abortController = null;
  let currentProducers = [];

  function clearList(list) {
    while (list.firstChild) list.removeChild(list.firstChild);
    list.hidden = true;
  }

  // Editing the search text after a pick must clear both hidden inputs, so a
  // stale product id can never be submitted alongside an edited name.
  function clearSelection() {
    productField.value = '';
    producerConfirmedField.value = 'false';
    producerField.hidden = true;
    producerSearchInput.value = '';
    clearList(producerSuggestionsList);
    currentProducers = [];
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

  function activateOption(list, index) {
    const options = Array.from(list.children);
    options.forEach((el, i) => el.classList.toggle('active', i === index));
    if (options[index]) options[index].scrollIntoView({ block: 'nearest' });
  }

  function attachKeyboardNav(input, list, onPickIndex) {
    let activeIndex = -1;
    input.addEventListener('keydown', (event) => {
      const options = Array.from(list.children);
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

  function pickProducer(producer) {
    productField.value = String(producer.product_id);
    producerConfirmedField.value = 'true';
    producerSearchInput.value = producer.holder;
    clearList(producerSuggestionsList);
  }

  function renderProducerOptions(filterText) {
    const needle = filterText.trim().toLowerCase();
    const matches = currentProducers.filter((producer) =>
      producer.holder.toLowerCase().includes(needle)
    );
    const options = matches.map((producer) =>
      makeOption(producer.holder, () => pickProducer(producer))
    );
    renderList(producerSuggestionsList, options);
  }

  function pickPresentation(presentation) {
    searchInput.value = [presentation.name, presentation.strength, presentation.form]
      .filter(Boolean)
      .join(' — ');
    clearList(suggestionsList);
    productField.value = String(presentation.default_product_id);
    currentProducers = presentation.producers;

    if (presentation.producers.length > 1) {
      // Several producers and nothing picked yet: the tiebreak default is
      // stored, but not presented as fact — see Item.producer_confirmed.
      producerConfirmedField.value = 'false';
      producerField.hidden = false;
      producerSearchInput.value = '';
      clearList(producerSuggestionsList);
    } else {
      // A single holder means the tiebreak had nothing to choose between,
      // so the value is necessarily correct — confirming it would be a
      // question with one answer.
      producerConfirmedField.value = 'true';
      producerField.hidden = true;
    }
  }

  function renderPresentationOptions(presentations) {
    const options = presentations.map((presentation) => {
      const label = [presentation.name, presentation.strength, presentation.form]
        .filter(Boolean)
        .join(' — ');
      return makeOption(label, () => pickPresentation(presentation));
    });
    renderList(suggestionsList, options);
  }

  async function fetchSuggestions(query) {
    const mySequence = ++sequence;
    if (abortController) abortController.abort();
    abortController = new AbortController();
    try {
      const response = await fetch(
        `/suggestions/?q=${encodeURIComponent(query)}`,
        { signal: abortController.signal }
      );
      const data = await response.json();
      // A slower, superseded response must never overwrite a newer one.
      if (mySequence < latestRenderedSequence) return;
      latestRenderedSequence = mySequence;
      renderPresentationOptions(data.results);
    } catch (error) {
      if (error.name !== 'AbortError') throw error;
    }
  }

  searchInput.addEventListener('input', () => {
    clearSelection();
    if (debounceTimer) clearTimeout(debounceTimer);
    const query = searchInput.value.trim();
    if (query.length < 2) {
      clearList(suggestionsList);
      return;
    }
    debounceTimer = setTimeout(() => fetchSuggestions(query), DEBOUNCE_MS);
  });

  producerSearchInput.addEventListener('input', () => {
    // Client-side filtering over the already-delivered producer list: no
    // second endpoint, no second request. The product field keeps the
    // tiebreak default until a producer option is actually picked.
    producerConfirmedField.value = 'false';
    renderProducerOptions(producerSearchInput.value);
  });

  attachKeyboardNav(searchInput, suggestionsList, (index) => {
    const li = suggestionsList.children[index];
    if (li) li.dispatchEvent(new MouseEvent('mousedown'));
  });
  attachKeyboardNav(producerSearchInput, producerSuggestionsList, (index) => {
    const li = producerSuggestionsList.children[index];
    if (li) li.dispatchEvent(new MouseEvent('mousedown'));
  });
})();
