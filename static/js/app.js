// Toast notification
function showToast(msg, type = "success") {
  const icons = { success: "✓", error: "✗", info: "ℹ" };
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.innerHTML = `<span>${icons[type] || "●"}</span> ${msg}`;
  document.body.appendChild(t);
  setTimeout(() => (t.style.opacity = "0"), 2500);
  setTimeout(() => t.remove(), 2800);
}

// Confirm delete
document.querySelectorAll(".confirm-delete").forEach((form) => {
  form.addEventListener("submit", (e) => {
    if (
      !confirm(
        "Are you sure you want to delete this? This action cannot be undone.",
      )
    ) {
      e.preventDefault();
    }
  });
});
