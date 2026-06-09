(function () {
  const storageKey = "sidebar-collapsed";
  const toggle = document.getElementById("sidebar-toggle");

  function setCollapsed(collapsed) {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    if (toggle) {
      toggle.setAttribute("aria-expanded", String(!collapsed));
      toggle.setAttribute(
        "aria-label",
        collapsed ? "Expand menu" : "Collapse menu"
      );
    }
  }

  if (localStorage.getItem(storageKey) === "true") {
    setCollapsed(true);
  }

  toggle?.addEventListener("click", function () {
    const collapsed = !document.body.classList.contains("sidebar-collapsed");
    setCollapsed(collapsed);
    localStorage.setItem(storageKey, String(collapsed));
  });
})();
