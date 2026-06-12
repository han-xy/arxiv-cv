const state = {
  papers: [],
  query: "",
  language: "both",
  sort: "newest",
  meta: null,
};

const DATA_URL = "data/papers.json";

const els = {
  list: document.querySelector("#paperList"),
  template: document.querySelector("#paperTemplate"),
  status: document.querySelector("#statusText"),
  meta: document.querySelector("#metaText"),
  search: document.querySelector("#searchInput"),
  language: document.querySelector("#languageSelect"),
  sort: document.querySelector("#sortSelect"),
  refresh: document.querySelector("#refreshBtn"),
};

function formatDate(value) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function textForSearch(paper) {
  return [
    paper.title_en,
    paper.title_zh,
    paper.summary_en,
    paper.summary_zh,
    ...(paper.authors || []),
    ...(paper.categories || []),
  ]
    .join(" ")
    .toLowerCase();
}

function filteredPapers() {
  const query = state.query.trim().toLowerCase();
  const papers = query
    ? state.papers.filter((paper) => textForSearch(paper).includes(query))
    : [...state.papers];

  if (state.sort === "title") {
    papers.sort((a, b) => (a.title_en || "").localeCompare(b.title_en || ""));
  } else {
    papers.sort((a, b) => new Date(b.published || 0) - new Date(a.published || 0));
  }
  return papers;
}

function translationFallback(paper, kind) {
  if (paper.translation_status === "missing_api_key") {
    return kind === "title" ? "未配置翻译服务" : "仓库 Secrets 配置 OPENAI_API_KEY 后会生成中文翻译。";
  }
  return kind === "title" ? paper.title_en : paper.summary_en;
}

function renderTags(container, paper) {
  container.replaceChildren();
  for (const category of paper.categories || []) {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = category;
    container.append(tag);
  }
  const published = document.createElement("span");
  published.className = "tag";
  published.textContent = `发布 ${formatDate(paper.published)}`;
  container.append(published);
}

function render() {
  document.body.classList.toggle("lang-zh", state.language === "zh");
  document.body.classList.toggle("lang-en", state.language === "en");

  const papers = filteredPapers();
  els.list.replaceChildren();
  els.status.textContent = papers.length ? `共 ${papers.length} 篇论文` : "没有匹配的论文";

  if (state.meta?.last_updated) {
    els.meta.textContent = `最后更新 ${formatDate(state.meta.last_updated)}`;
  } else if (state.meta?.last_error) {
    els.meta.textContent = `更新失败：${state.meta.last_error}`;
  } else {
    els.meta.textContent = "";
  }

  if (!papers.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "暂时没有论文数据。";
    els.list.append(empty);
    return;
  }

  for (const paper of papers) {
    const node = els.template.content.cloneNode(true);
    node.querySelector(".paper-id").textContent = paper.id || "arXiv";
    node.querySelector(".title-zh").textContent =
      paper.title_zh || translationFallback(paper, "title");
    node.querySelector(".title-en").textContent = paper.title_en || "";
    node.querySelector(".authors").textContent = (paper.authors || []).join(", ");
    node.querySelector(".summary-zh p").textContent =
      paper.summary_zh || translationFallback(paper, "summary");
    node.querySelector(".summary-en p").textContent = paper.summary_en || "";
    renderTags(node.querySelector(".tag-row"), paper);

    const absLink = node.querySelector(".abs-link");
    absLink.href = paper.abs_url || "#";
    const pdfLink = node.querySelector(".pdf-link");
    pdfLink.href = paper.pdf_url || paper.abs_url || "#";

    els.list.append(node);
  }
}

async function loadPapers() {
  els.status.textContent = "正在加载论文...";
  const cacheBust = `?t=${Date.now()}`;
  const response = await fetch(`${DATA_URL}${cacheBust}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`加载失败：${response.status}`);
  const data = await response.json();
  state.papers = data.papers || [];
  state.meta = data;
  render();
}

async function refreshPapers() {
  els.refresh.disabled = true;
  els.refresh.querySelector("span").textContent = "...";
  try {
    await loadPapers();
  } catch (error) {
    els.status.textContent = error.message;
  } finally {
    els.refresh.disabled = false;
    els.refresh.querySelector("span").textContent = "↻";
  }
}

els.search.addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});

els.language.addEventListener("change", (event) => {
  state.language = event.target.value;
  render();
});

els.sort.addEventListener("change", (event) => {
  state.sort = event.target.value;
  render();
});

els.refresh.addEventListener("click", refreshPapers);

loadPapers().catch((error) => {
  els.status.textContent = error.message;
});
