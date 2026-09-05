// Check-screen picker: a pick is a navigation, not a form fill.
//
// The check screen has no hidden fields, no producer step and nothing to
// submit — picking a suggestion just reloads the screen with the chosen
// product as `?product=`, which is the same URL the screen is already fully
// driveable by. Requires product-search.js to have loaded first.
(() => {
  'use strict';

  const searchInput = document.getElementById('product-search');
  if (!searchInput) return;

  const suggestionsList = document.getElementById('suggestions');
  // The route comes from the template's {% url %}, not from a path written out
  // again here: one definition of where the check screen lives.
  const resultUrl = searchInput.dataset.resultUrl;

  const { presentationLabel, attachPresentationSearch, clearList } = window.ProductSearch;

  attachPresentationSearch({
    input: searchInput,
    list: suggestionsList,
    onPick: (presentation) => {
      // Set before navigating so the field reads as picked while the next page
      // loads, rather than sitting on the half-typed query.
      searchInput.value = presentationLabel(presentation);
      clearList(suggestionsList);
      window.location = `${resultUrl}?product=${encodeURIComponent(
        presentation.default_product_id
      )}`;
    },
  });
})();
