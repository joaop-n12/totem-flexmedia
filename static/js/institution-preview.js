/* Admin CSP blocks inline scripts; keep the preview handler in this file. */
document.addEventListener('DOMContentLoaded', () => {
  [['pc_picker', 'pc'], ['sc_picker', 'sc'], ['bc_picker', 'bc'], ['tc_picker', 'tc']]
    .forEach(([pickerId, textId]) => {
      const picker = document.getElementById(pickerId);
      const text = document.getElementById(textId);
      if (!picker || !text) return;

      // Mantem o seletor e o hex sincronizados sem handlers inline, que a CSP bloqueia.
      const syncPickerFromText = () => {
        if (/^#[0-9a-f]{6}$/i.test(text.value.trim())) {
          picker.value = text.value.trim();
        }
      };
      syncPickerFromText();
      picker.addEventListener('input', () => { text.value = picker.value; });
      text.addEventListener('input', syncPickerFromText);
      text.addEventListener('change', syncPickerFromText);
    });

  const button = document.getElementById('previewBtn');
  if (!button) return;

  button.addEventListener('click', () => {
    const sourceForm = button.closest('form');
    const target = `institution-preview-${Date.now()}`;
    const previewWindow = window.open('', target);
    if (!previewWindow) {
      window.alert('Permita pop-ups para abrir a pré-visualização.');
      return;
    }

    const form = document.createElement('form');
    form.method = 'POST';
    form.action = button.dataset.previewUrl;
    form.target = target;

    const names = [
      'name', 'slug', 'type', 'primary_color', 'secondary_color',
      'bg_color', 'text_color', 'theme', 'tagline', 'ai_name'
    ];
    const appendValue = (name, value) => {
      const input = document.createElement('input');
      input.type = 'hidden';
      input.name = name;
      input.value = value || '';
      form.appendChild(input);
    };

    const csrf = sourceForm.querySelector('[name="_csrf_token"]');
    if (csrf) appendValue('_csrf_token', csrf.value);
    names.forEach((name) => {
      const field = sourceForm.querySelector(`[name="${name}"]`);
      if (field) appendValue(name, field.value);
    });
    sourceForm.querySelectorAll('[name="modules"]:checked').forEach((field) => {
      appendValue('modules', field.value);
    });
    sourceForm.querySelectorAll('[name^="order_"]').forEach((field) => {
      appendValue(field.name, field.value);
    });

    document.body.appendChild(form);
    form.submit();
    form.remove();
  });
});
