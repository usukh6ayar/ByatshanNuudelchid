/* Shared UI-states helpers (2026-08-19) — the JS half of the toast,
 * loading-button and skeleton conventions documented in app.css under
 * "UI STATES — shared standard for every new screen/form". Loaded on
 * every page (base_teacher.html, base_parent.html, base_admin.html) so
 * a new screen can call these without wiring anything of its own.
 *
 * window.showToast(message, type)   — type is "ok" (default) or "error".
 *   Auto-dismisses after 3s. Use for a client-side confirmation of an
 *   action that isn't a full page reload (a real server-rendered
 *   redirect already gets a `.msg` banner from Django's messages
 *   framework — this is for everything else).
 *
 * window.setButtonLoading(button, isLoading) — toggles the spinner
 *   state from CLAUDE.md §5's "loading state for slow actions" and
 *   disables the button so a slow request can't be double-submitted.
 *
 * Every real `<form method="post">` in the app (30+ templates, and any
 * future one) also gets the loading-button treatment automatically —
 * see the document-level "submit" listener at the bottom. A form whose
 * own script calls `event.preventDefault()` (the client-only prep
 * screens — chat send, survey publish, attendance leave, and so on)
 * is left alone: by the time this listener runs the submit has
 * already bubbled past the form's own handler, so `defaultPrevented`
 * is accurate. A form that genuinely doesn't want this (none do today)
 * can opt out with `data-no-auto-loading`.
 */
(function () {
  function ensureStack() {
    var stack = document.querySelector('[data-toast-stack]');
    if (stack) return stack;
    stack = document.createElement('div');
    stack.className = 'toast-stack';
    stack.setAttribute('data-toast-stack', '');
    stack.setAttribute('aria-live', 'polite');
    document.body.appendChild(stack);
    return stack;
  }

  window.showToast = function (message, type) {
    var stack = ensureStack();
    var toast = document.createElement('div');
    toast.className = 'toast toast--' + (type === 'error' ? 'error' : 'ok');
    toast.textContent = message;
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    stack.appendChild(toast);
    window.requestAnimationFrame(function () { toast.classList.add('is-shown'); });
    window.setTimeout(function () {
      toast.classList.remove('is-shown');
      window.setTimeout(function () { toast.remove(); }, 200);
    }, 3000);
    return toast;
  };

  window.setButtonLoading = function (button, isLoading) {
    if (!button) return;
    button.classList.toggle('is-loading', !!isLoading);
    button.disabled = !!isLoading;
  };

  document.addEventListener('submit', function (event) {
    if (event.defaultPrevented) return;
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || form.hasAttribute('data-no-auto-loading')) return;
    var button = event.submitter
      || form.querySelector('button[type="submit"], input[type="submit"], button:not([type])');
    if (button && !button.disabled) window.setButtonLoading(button, true);
  });
}());
