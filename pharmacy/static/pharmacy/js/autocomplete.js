// Add-screen picker: everything that fills this form's hidden fields.
//
// The search half — debounce, fetch, sequence guard, keyboard nav, option
// rendering — lives in product-search.js, which must load first. What stays
// here is what only the add screen has: a product field, a producer step, and
// the Item.producer_confirmed distinction between "the user picked this
// producer" and "this was the tiebreak default".
(() => {
  'use strict';

  const searchInput = document.getElementById('product-search');
  if (!searchInput) return;

  const {
    clearList,
    makeOption,
    renderList,
    optionsOf,
    attachKeyboardNav,
    presentationLabel,
    attachPresentationSearch,
  } = window.ProductSearch;

  const suggestionsList = document.getElementById('suggestions');
  const productField = document.getElementById('id_product');
  const producerConfirmedField = document.getElementById('id_producer_confirmed');
  const producerField = document.getElementById('producer-field');
  const producerSearchInput = document.getElementById('producer-search');
  const producerSuggestionsList = document.getElementById('producer-suggestions');

  let currentProducers = [];

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
    searchInput.value = presentationLabel(presentation);
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

  attachPresentationSearch({
    input: searchInput,
    list: suggestionsList,
    onPick: pickPresentation,
    onInput: clearSelection,
  });

  // The producer picker deliberately does not go through the shared path: it
  // filters an already-delivered list in memory, with no debounce, no fetch and
  // no second endpoint. Routing it through `attachPresentationSearch` would
  // change its behaviour to buy a symmetry no screen benefits from.
  producerSearchInput.addEventListener('input', () => {
    // The product field keeps the tiebreak default until a producer option is
    // actually picked.
    producerConfirmedField.value = 'false';
    renderProducerOptions(producerSearchInput.value);
  });

  // Focusing the empty field lists every holder, because an empty needle
  // matches all of them. Without this the only way to see the options is to
  // guess a substring of a name you are trying to look up — and unlike the drug
  // search, this list is already in memory and bounded (10 holders at the
  // registry's worst), so there is nothing to debounce and no request to spare.
  producerSearchInput.addEventListener('focus', () => {
    renderProducerOptions(producerSearchInput.value);
  });

  attachKeyboardNav(producerSearchInput, producerSuggestionsList, (index) => {
    const li = optionsOf(producerSuggestionsList)[index];
    if (li) li.dispatchEvent(new MouseEvent('mousedown'));
  });
})();
