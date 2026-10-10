(() => {
  const nav = document.createElement("nav");
  nav.className = "hub-navigation";
  nav.setAttribute("aria-label", "Hub");
  const links = [["Pathology Hub", "/"], ["Teaching topics", "/content/"], ["Lecture clips", "/lectures/"], ["Reference library ↗", "https://chat.pathologynotebook.com/"]];
  for (const [label, href] of links) {
    const a = document.createElement("a");
    a.textContent = label; a.href = href;
    if (window.location.pathname === href) a.setAttribute("aria-current", "page");
    nav.append(a);
  }
  document.body.prepend(nav);
  document.querySelector(".back")?.remove();
})();
