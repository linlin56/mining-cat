// What the pages share on top of Bootstrap: a message dialog (a modal) and toasts.
"use strict";

window.MiningCatUI = (() => {
  let modal = null;
  let queue = Promise.resolve();

  function messageModal() {
    if (modal) return modal;
    modal = document.createElement("div");
    modal.className = "modal";
    modal.tabIndex = -1;
    modal.setAttribute("aria-labelledby", "mc-dialog-title");
    modal.innerHTML = `
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h2 class="modal-title fs-5" id="mc-dialog-title"></h2>
            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body"><p class="mc-pre-line mb-0"></p></div>
          <div class="modal-footer"></div>
        </div>
      </div>`;
    document.body.append(modal);
    return modal;
  }

  // Resolves to the value of the button clicked, as a string ("" when the dialog is dismissed). One dialog at a
  // time: the next ones wait for it to close. buttons: [{label, value, primary}]
  function dialog(title, message, buttons = [{ label: "OK", value: true, primary: true }]) {
    const answer = queue.then(() => new Promise((resolve) => {
      const box = messageModal();
      const instance = bootstrap.Modal.getOrCreateInstance(box);
      let value = "";
      box.querySelector(".modal-title").textContent = title;
      box.querySelector(".modal-body p").textContent = message;
      box.querySelector(".modal-footer").replaceChildren(...buttons.map((b) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = b.primary ? "btn btn-primary" : "btn btn-outline-secondary";
        button.textContent = b.label;
        button.addEventListener("click", () => { value = String(b.value); instance.hide(); });
        return button;
      }));
      box.addEventListener("hidden.bs.modal", () => resolve(value), { once: true });
      instance.show();
      box.querySelector(".modal-footer .btn-primary")?.focus();
    }));
    queue = answer.catch(() => {});
    return answer;
  }

  // A modal of the page (without .fade: shown and hidden at once).
  const showModal = (element) => bootstrap.Modal.getOrCreateInstance(element).show();
  const hideModal = (element) => bootstrap.Modal.getOrCreateInstance(element).hide();
  const isModalOpen = () => Boolean(document.querySelector(".modal.show"));

  // kind: "info", "success" or "error"
  const TOAST_COLOURS = { info: "text-bg-dark", success: "text-bg-success", error: "text-bg-danger" };
  let toastBox = null;

  function toast(message, kind = "info") {
    if (!toastBox) {
      const container = document.createElement("div");
      container.className = "toast-container position-fixed bottom-0 start-50 translate-middle-x p-3";
      toastBox = document.createElement("div");
      toastBox.setAttribute("role", "status");
      toastBox.setAttribute("aria-live", "polite");
      toastBox.innerHTML = '<div class="d-flex"><div class="toast-body"></div>'
        + '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>';
      container.append(toastBox);
      document.body.append(container);
    }
    toastBox.className = `toast align-items-center border-0 ${TOAST_COLOURS[kind] || TOAST_COLOURS.info}`;
    toastBox.querySelector(".toast-body").textContent = message;
    // shown again from the start (and for the whole delay) when a toast is already up
    bootstrap.Toast.getOrCreateInstance(toastBox, { delay: 3500 }).show();
  }

  return { dialog, showModal, hideModal, isModalOpen, toast };
})();
