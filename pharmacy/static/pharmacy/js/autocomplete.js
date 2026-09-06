(() => {
  'use strict';

  const searchInput = document.getElementById('product-search');
  if (!searchInput) return;

  const {
    clearList,
    presentationLabel,
    attachPresentationSearch,
  } = window.ProductSearch;

  const suggestionsList = document.getElementById('suggestions');
  const productField = document.getElementById('id_product');
  const producerConfirmedField = document.getElementById('id_producer_confirmed');
  const producerField = document.getElementById('producer-field');
  const producerSelect = document.getElementById('producer-select');
  const substancePreview = document.getElementById('substance-preview');
  const submitBtn = document.getElementById('submit-btn');
  const searchTextHidden = document.getElementById('search-text-hidden');

  function clearSelection() {
    productField.value = '';
    producerConfirmedField.value = 'false';
    producerField.hidden = true;
    if (producerSelect) {
      producerSelect.hidden = true;
      producerSelect.innerHTML = '<option value="">Wybierz producenta (opcjonalnie)</option>';
    }
    if (substancePreview) {
      substancePreview.hidden = true;
      substancePreview.textContent = '';
    }
    if (submitBtn) submitBtn.disabled = true;
  }

  function pickPresentation(presentation) {
    searchInput.value = presentationLabel(presentation);
    clearList(suggestionsList);
    productField.value = String(presentation.default_product_id);

    if (submitBtn) submitBtn.disabled = false;

    if (substancePreview && presentation.substances.length > 0) {
      substancePreview.textContent = 'Substancje czynne: ' + presentation.substances.join(', ');
      substancePreview.hidden = false;
    }

    if (presentation.producers.length > 1 && producerSelect) {
      producerConfirmedField.value = 'false';
      producerField.hidden = false;
      producerSelect.innerHTML = '<option value="">Wybierz producenta (opcjonalnie)</option>';
      presentation.producers.forEach(function(producer) {
        var opt = document.createElement('option');
        opt.value = String(producer.product_id);
        opt.textContent = producer.holder;
        producerSelect.appendChild(opt);
      });
      producerSelect.hidden = false;
    } else {
      producerConfirmedField.value = 'true';
      producerField.hidden = true;
    }
  }

  if (producerSelect) {
    producerSelect.addEventListener('change', function() {
      if (this.value) {
        productField.value = this.value;
        producerConfirmedField.value = 'true';
      } else {
        producerConfirmedField.value = 'false';
      }
    });
  }

  searchInput.addEventListener('input', function() {
    if (searchTextHidden) searchTextHidden.value = this.value;
  });

  attachPresentationSearch({
    input: searchInput,
    list: suggestionsList,
    onPick: pickPresentation,
    onInput: clearSelection,
  });
})();
