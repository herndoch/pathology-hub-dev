(() => {
  const nav = document.createElement("nav");
  nav.className = "hub-navigation";
  nav.setAttribute("aria-label", "Hub");
  const links = [
    ["Videos", "/videos/", "nav-videos", "Video index"],
    ["Teaching topics", "/content/", "", "Teaching topics"],
    ["Lecture clips", "/lectures/", "", "Lecture clips"],
    ["Reference library ↗", "https://chat.pathologynotebook.com/", "", ""],
  ];
  const here = window.location.pathname.replace(/index\.html$/, "");
  const brand = document.createElement("a");
  brand.className = "hub-brand"; brand.href = "/";
  const name = document.createElement("b"); name.textContent = "Pathology Knowledge Hub";
  const section = document.createElement("small");
  const current = links.find(([, href]) => here === href);
  section.textContent = current ? current[3] : "Pathology Notebook";
  brand.append(name, section);
  const list = document.createElement("div");
  list.className = "hub-links";
  for (const [label, href, cls] of links) {
    const a = document.createElement("a");
    a.textContent = label; a.href = href;
    if (cls) a.className = cls;
    if (here === href) a.setAttribute("aria-current", "page");
    list.append(a);
  }
  nav.append(brand, list);
  document.body.prepend(nav);
  document.querySelector(".back")?.remove();
})();
