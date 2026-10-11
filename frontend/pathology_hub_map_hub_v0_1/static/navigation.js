(() => {
  const nav = document.createElement("nav");
  nav.className = "hub-navigation";
  nav.setAttribute("aria-label", "Hub");
  const links = [
    ["Pathology Knowledge Hub", "/", ""],
    ["Videos", "/videos/", "nav-videos"],
    ["Teaching topics", "/content/", ""],
    ["Lecture clips", "/lectures/", ""],
    ["Reference library ↗", "https://chat.pathologynotebook.com/", ""],
  ];
  const here = window.location.pathname.replace(/index\.html$/, "");
  for (const [label, href, cls] of links) {
    const a = document.createElement("a");
    a.textContent = label; a.href = href;
    if (cls) a.className = cls;
    if (here === href) a.setAttribute("aria-current", "page");
    nav.append(a);
  }
  document.body.prepend(nav);
  document.querySelector(".back")?.remove();
})();
