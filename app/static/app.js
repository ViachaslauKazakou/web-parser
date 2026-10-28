(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const labels = { high: "Высокая", medium: "Средняя", low: "Низкая", offtopic: "Вне темы" };
  const featureNames = {
    similarity_title: "Заголовок",
    similarity_description: "Описание",
    similarity_first_message: "Стартовый пост",
    lexical_overlap: "Совпадение слов",
  };
  const pageTitles = { workspace: "Рабочая область", parser: "Посты автора", history: "История" };

  let parsedTopic = null;
  let currentAnalysis = null;
  let latestUserSearch = null;
  let toastTimer = null;

  function showToast(message, kind = "") {
    const region = $("#toast-region");
    const toast = document.createElement("div");
    toast.className = `toast${kind ? ` is-${kind}` : ""}`;
    toast.setAttribute("role", kind === "error" ? "alert" : "status");
    toast.textContent = String(message || "Произошла ошибка.");
    region.replaceChildren(toast);
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.remove(), 5200);
  }

  async function requestJson(url, options = {}) {
    let response;
    try {
      response = await fetch(url, options);
    } catch (_error) {
      throw new Error("Не удалось связаться с приложением. Проверьте, что сервис запущен.");
    }
    let body;
    try {
      body = await response.json();
    } catch (_error) {
      body = {};
    }
    if (!response.ok) {
      const detail = body.detail;
      const message = Array.isArray(detail)
        ? detail.map((item) => item.msg || "Некорректные данные").join("; ")
        : detail || body.message || `Ошибка запроса (${response.status}).`;
      throw new Error(message);
    }
    return body;
  }

  function setBusy(button, busy, pendingLabel = "Выполняется…") {
    if (!button) return;
    if (busy) {
      button.dataset.originalLabel = button.textContent.trim();
      button.classList.add("is-loading");
      button.disabled = true;
      button.textContent = pendingLabel;
    } else {
      button.classList.remove("is-loading");
      button.disabled = false;
      if (button.dataset.originalLabel) button.textContent = button.dataset.originalLabel;
      delete button.dataset.originalLabel;
    }
  }

  function showView(name) {
    if (!pageTitles[name]) return;
    $$("[data-view-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.viewPanel !== name;
    });
    $$("[data-view-link]").forEach((link) => {
      const active = link.dataset.viewLink === name;
      link.classList.toggle("is-active", active);
      if (active && link.matches(".nav-link")) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    $("#current-location").textContent = pageTitles[name];
    if (name === "history") loadHistory();
  }

  function setStatus(healthy, label, detail) {
    const dot = $("#service-dot");
    const topDot = $("#top-status-dot");
    dot.classList.toggle("is-good", healthy);
    dot.classList.toggle("is-bad", !healthy);
    topDot.classList.toggle("is-good", healthy);
    topDot.classList.toggle("is-bad", !healthy);
    $("#service-label").textContent = label;
    $("#service-detail").textContent = detail;
    $("#top-status-text").textContent = healthy ? "Готов к работе" : "Нет соединения";
  }

  async function checkHealth() {
    try {
      await requestJson("/api/health", { headers: { Accept: "application/json" } });
      setStatus(true, "База данных подключена", "История сохраняется");
    } catch (_error) {
      setStatus(false, "База данных недоступна", "Проверьте Docker Compose");
    }
  }

  function readAnalysisOptions() {
    return {
      use_community_weight: $("#use-community").checked,
      use_llm_scoring: $("#use-llm-scoring").checked,
      use_llm_explain: $("#use-llm-explain").checked,
      llm_score_weight: Number($("#llm-weight")?.value || 35) / 100,
    };
  }

  function safePercent(value) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.max(0, Math.min(100, Math.round(number * 100))) : 0;
  }

  function textNode(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
  }

  function renderFeatures(features) {
    const details = textNode("div", "feature-details");
    Object.entries(featureNames).forEach(([key, label]) => {
      const meter = textNode("div", "feature-meter");
      meter.append(textNode("span", "", label));
      meter.append(textNode("strong", "", `${safePercent(features?.[key])}%`));
      details.append(meter);
    });
    if (features?.llm_score !== undefined && features?.llm_score !== null) {
      const meter = textNode("div", "feature-meter");
      meter.append(textNode("span", "", "LLM"));
      meter.append(textNode("strong", "", `${safePercent(features.llm_score)}%`));
      details.append(meter);
    }
    return details;
  }

  function renderOneResult(item) {
    const article = textNode("article", "reply-row");
    article.classList.toggle("is-best", item.rank_position === 1);
    article.dataset.label = item.relevance_label;

    const topline = textNode("div", "reply-topline");
    topline.append(textNode("span", "rank-number", item.rank_position));
    const authorLine = textNode("div", "reply-author");
    authorLine.append(document.createTextNode(item.author || "Автор не указан"));
    const state = textNode("span", `reply-state relevance-${item.relevance_label}`, labels[item.relevance_label] || "Не определено");
    authorLine.append(state);
    topline.append(authorLine);
    const score = textNode("span", "reply-score");
    score.append(document.createTextNode(String(safePercent(item.final_score))));
    score.append(textNode("small", "", "/ 100"));
    topline.append(score);
    article.append(topline);

    article.append(textNode("p", "reply-content", item.content));
    const rulerWrap = textNode("div", "ruler-wrap");
    const ruler = textNode("div", "ruler-track");
    ruler.setAttribute("role", "img");
    ruler.setAttribute("aria-label", `Оценка релевантности ${safePercent(item.final_score)} из 100`);
    const fill = textNode("span", "ruler-fill");
    fill.style.width = `${safePercent(item.final_score)}%`;
    const marker = textNode("span", "ruler-marker");
    marker.style.left = `${safePercent(item.final_score)}%`;
    ruler.append(fill, marker);
    rulerWrap.append(ruler);
    const scale = textNode("div", "ruler-scale");
    ["0", "25", "50", "75", "100"].forEach((value) => scale.append(textNode("span", "", value)));
    rulerWrap.append(scale);
    article.append(rulerWrap);

    const actions = textNode("div", "reply-actions");
    actions.append(textNode("span", "", item.explanation_short || ""));
    const toggle = textNode("button", "detail-toggle", "Показать факторы");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    const details = renderFeatures(item.features || {});
    details.hidden = true;
    toggle.addEventListener("click", () => {
      details.hidden = !details.hidden;
      toggle.textContent = details.hidden ? "Показать факторы" : "Скрыть факторы";
      toggle.setAttribute("aria-expanded", String(!details.hidden));
    });
    actions.append(toggle);
    article.append(actions, details);
    return article;
  }

  function renderAnalysis(data) {
    currentAnalysis = data;
    parsedTopic = null;
    $("#parse-preview").hidden = true;
    $("#ranked-results").replaceChildren();
    $("#results-section").hidden = false;
    $("#empty-results").hidden = true;
    $("#result-context").textContent = `${data.messages_count} ответов · ${data.source_type === "parsed" ? "форумный парсер" : "ручной источник"} · запуск #${data.id}`;
    $("#results-title").textContent = data.topic_title || "Ранжирование ответов";
    $("#result-filter").value = "all";

    const summaries = $("#analysis-summaries");
    summaries.hidden = !data.best_summary && !data.worst_summary;
    $("#best-summary").textContent = data.best_summary || "Пояснение не сформировано.";
    $("#worst-summary").textContent = data.worst_summary || "Пояснение не сформировано.";

    const warnings = $("#analysis-warnings");
    warnings.replaceChildren();
    warnings.hidden = !data.warnings?.length;
    (data.warnings || []).forEach((warning) => warnings.append(textNode("p", "", warning)));

    data.results.forEach((item) => $("#ranked-results").append(renderOneResult(item)));
    updateResultFilter();
    $("#workspace-title").textContent = "Результат анализа";
    checkHealth();
    loadHistoryCount();
  }

  function updateResultFilter() {
    const selected = $("#result-filter").value;
    const rows = $$(".reply-row", $("#ranked-results"));
    let visible = 0;
    rows.forEach((row) => {
      const show = selected === "all" || row.dataset.label === selected;
      row.hidden = !show;
      if (show) visible += 1;
    });
    $("#result-count").textContent = `${visible} из ${rows.length} ответов`;
  }

  async function analyzePayload(payload, button, label = "Считаем релевантность…") {
    setBusy(button, true, label);
    try {
      const data = await requestJson("/api/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      });
      renderAnalysis(data);
      showToast("Результат сохранён в истории анализов.", "success");
      return data;
    } catch (error) {
      showToast(error.message, "error");
      throw error;
    } finally {
      setBusy(button, false);
    }
  }

  function displayParsedTopic(data) {
    parsedTopic = data;
    $("#preview-title").textContent = data.title || "Тема без заголовка";
    $("#preview-description").textContent = data.description || "Описание не найдено.";
    $("#preview-first-message").textContent = data.first_message || "Стартовое сообщение не найдено.";
    $("#preview-count").textContent = `${data.messages?.length || 0} ответов`;
    $("#parse-preview").hidden = false;
    $("#analyze-parsed").disabled = !data.messages?.length;
    $("#parse-preview").scrollIntoView({ behavior: "smooth", block: "nearest" });
    if (data.warning) showToast(`Парсинг остановлен по защитному лимиту: ${data.warning}`);
  }

  function optionsForManual() {
    return {
      use_community_weight: $(".option-community").checked,
      use_llm_scoring: $(".option-llm-scoring").checked,
      use_llm_explain: $(".option-llm-explain").checked,
      llm_score_weight: Number($("#llm-weight")?.value || 35) / 100,
    };
  }

  function optionsForUpload() {
    return {
      use_community_weight: $(".file-option-community").checked,
      use_llm_scoring: $(".file-option-llm-scoring").checked,
      use_llm_explain: $(".file-option-llm-explain").checked,
    };
  }

  function splitManualReplies(text) {
    return text
      .split(/\n\s*\n+/)
      .map((block) => block.trim())
      .filter(Boolean)
      .map((block, index) => {
        const lines = block.split("\n");
        const firstLine = lines[0].trim();
        const authorMatch = firstLine.match(/^(?:автор|author)\s*:\s*(.*)$/i);
        if (authorMatch) {
          lines.shift();
          return { external_id: `manual-${index + 1}`, author: authorMatch[1].trim() || null, content: lines.join("\n").trim() };
        }
        return { external_id: `manual-${index + 1}`, content: block };
      })
      .filter((message) => message.content);
  }

  function downloadBlob(blob, filename) {
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function downloadParserResult() {
    if (!latestUserSearch) return;
    const grouped = {};
    latestUserSearch.messages.forEach((message) => {
      const key = message.theme_name || "Без темы";
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push({ date: message.date, message: message.message, url: message.url, section: message.section });
    });
    const exportData = { User: latestUserSearch.user, messages: grouped };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json;charset=utf-8" });
    const safeName = String(latestUserSearch.user || "user").replace(/[^\p{L}\p{N}_-]/gu, "_");
    downloadBlob(blob, `parser_${safeName || "user"}.json`);
  }

  function renderParserResults(data) {
    latestUserSearch = data;
    $("#parser-empty").hidden = true;
    $("#parser-results").hidden = false;
    $("#parser-results-count").textContent = `${data.messages_count} сообщений · ${data.mode === "comments" ? "по ID пользователя" : "по поисковому запросу"}`;
    const list = $("#parser-message-list");
    list.replaceChildren();
    data.messages.forEach((message) => {
      const article = textNode("article", "parser-message");
      article.append(textNode("h3", "", message.theme_name || "Без темы"));
      const meta = textNode("div", "parser-message-meta");
      meta.append(textNode("span", "", message.section || "Форум"));
      meta.append(textNode("span", "", "·"));
      meta.append(textNode("time", "", formatDate(message.date)));
      article.append(meta, textNode("p", "", message.message || ""));
      if (isSafeForumLink(message.url)) {
        const link = document.createElement("a");
        link.href = message.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.append(document.createTextNode("Открыть тему"));
        const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        icon.setAttribute("aria-hidden", "true");
        const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
        use.setAttribute("href", "#icon-external");
        icon.append(use);
        link.append(icon);
        article.append(link);
      }
      list.append(article);
    });
  }

  function isSafeForumLink(value) {
    try {
      return new URL(value, window.location.origin).protocol === "https:";
    } catch (_error) {
      return false;
    }
  }

  function formatDate(value) {
    if (!value) return "Дата не указана";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("ru-RU", { dateStyle: "medium" });
  }

  function sourceLabel(type) {
    return type === "parsed" ? "Парсер" : "Ручной ввод / файл";
  }

  async function loadHistoryCount() {
    try {
      const rows = await requestJson("/api/runs?limit=100");
      const count = rows.length;
      const badge = $("#history-count");
      badge.textContent = count;
      badge.hidden = count === 0;
    } catch (_error) {
      // Health status already communicates database availability.
    }
  }

  function renderHistory(rows) {
    const body = $("#history-body");
    body.replaceChildren();
    $("#empty-history").hidden = rows.length !== 0;
    $(".history-table").hidden = rows.length === 0;
    $("#history-summary").textContent = rows.length ? `${rows.length} последних анализов` : "История пока пуста";
    const badge = $("#history-count");
    badge.textContent = rows.length;
    badge.hidden = rows.length === 0;

    rows.forEach((run) => {
      const row = document.createElement("tr");
      const titleCell = document.createElement("td");
      const titleButton = textNode("button", "history-topic-button", run.topic_title);
      titleButton.type = "button";
      titleButton.title = run.topic_title;
      titleButton.dataset.openRun = run.id;
      titleCell.append(titleButton);
      row.append(titleCell);
      row.append(textNode("td", "", sourceLabel(run.source_type)));
      row.append(textNode("td", "", run.messages_count));
      row.append(textNode("td", "", run.best_score === null ? "—" : `${safePercent(run.best_score)} / 100`));
      row.append(textNode("td", "", formatDate(run.created_at)));
      const actionCell = document.createElement("td");
      const open = textNode("button", "history-open", "Открыть");
      open.type = "button";
      open.dataset.openRun = run.id;
      open.setAttribute("aria-label", `Открыть анализ: ${run.topic_title}`);
      actionCell.append(open);
      row.append(actionCell);
      body.append(row);
    });
  }

  async function loadHistory() {
    const button = $("#history-reload");
    setBusy(button, true, "Загружаю…");
    try {
      const rows = await requestJson("/api/runs?limit=100");
      renderHistory(rows);
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  }

  async function openSavedRun(runId) {
    try {
      const data = await requestJson(`/api/runs/${encodeURIComponent(runId)}`);
      showView("workspace");
      renderAnalysis(data);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function exportSavedRun(format) {
    if (!currentAnalysis?.id) return;
    try {
      const response = await fetch(`/api/runs/${currentAnalysis.id}/export.${format}`);
      if (!response.ok) throw new Error("Не удалось скачать экспорт.");
      const blob = await response.blob();
      downloadBlob(blob, `forumscope-analysis-${currentAnalysis.id}.${format}`);
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  $$("[data-view-link]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const view = link.dataset.viewLink;
      showView(view);
      if (view === "workspace" && currentAnalysis) $("#workspace-title").textContent = "Результат анализа";
    });
  });

  $$("[data-source-tab]").forEach((tab) => {
    tab.addEventListener("click", () => {
      $$("[data-source-tab]").forEach((item) => {
        const active = item === tab;
        item.classList.toggle("is-selected", active);
        item.setAttribute("aria-selected", String(active));
        item.tabIndex = active ? 0 : -1;
      });
      $$("[data-source-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.sourcePanel !== tab.dataset.sourceTab;
      });
    });
    tab.addEventListener("keydown", (event) => {
      const tabs = $$("[data-source-tab]");
      const index = tabs.indexOf(tab);
      let nextIndex = index;
      if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === "Home") nextIndex = 0;
      else if (event.key === "End") nextIndex = tabs.length - 1;
      else return;
      event.preventDefault();
      tabs[nextIndex].click();
      tabs[nextIndex].focus();
    });
  });

  $("#topic-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    parsedTopic = null;
    const button = $("#parse-topic-button");
    setBusy(button, true, "Собираю…");
    try {
      const result = await requestJson("/api/parser/topic", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          topic_url: $("#topic-url").value.trim(),
          max_messages: Number($("#max-messages").value || 0),
          max_pages: 20,
        }),
      });
      displayParsedTopic(result);
      showToast("Тема собрана. Проверьте ответы перед запуском анализа.", "success");
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  });

  $("#analyze-parsed").addEventListener("click", async (event) => {
    if (!parsedTopic?.messages?.length) return;
    const payload = {
      source_type: "parsed",
      source_url: parsedTopic.source_url,
      topic: {
        title: parsedTopic.title,
        description: parsedTopic.description,
        first_message_content: parsedTopic.first_message,
        external_id: parsedTopic.source_url,
      },
      messages: parsedTopic.messages,
      options: readAnalysisOptions(),
    };
    await analyzePayload(payload, event.currentTarget);
  });

  $("#reset-preview").addEventListener("click", () => {
    parsedTopic = null;
    $("#parse-preview").hidden = true;
    $("#topic-url").focus();
  });

  $("#upload-file").addEventListener("change", (event) => {
    const file = event.currentTarget.files?.[0];
    $("#upload-label").textContent = file ? `${file.name} · ${(file.size / 1024).toFixed(0)} КБ` : "Выберите файл JSON или CSV";
  });

  $("#upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = $("#upload-file").files?.[0];
    if (!file) {
      showToast("Сначала выберите JSON или CSV файл.", "error");
      return;
    }
    const button = $("#upload-form button[type='submit']");
    const form = new FormData();
    form.append("file", file);
    const uploadOptions = optionsForUpload();
    Object.entries(uploadOptions).forEach(([key, value]) => form.append(key, String(value)));
    setBusy(button, true, "Загружаю и оцениваю…");
    try {
      const data = await requestJson("/api/analysis/import", { method: "POST", body: form });
      renderAnalysis(data);
      showToast("Файл обработан, результат сохранён.", "success");
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  });

  $("#manual-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const replies = splitManualReplies($("#manual-replies").value);
    if (!replies.length) {
      showToast("Добавьте хотя бы один непустой ответ.", "error");
      return;
    }
    const payload = {
      source_type: "manual",
      topic: {
        title: $("#manual-title").value.trim(),
        description: $("#manual-description").value.trim() || null,
        first_message_content: $("#manual-first-message").value.trim() || null,
      },
      messages: replies,
      options: optionsForManual(),
    };
    await analyzePayload(payload, $("#manual-form button[type='submit']"));
  });

  $("#llm-weight").addEventListener("input", (event) => {
    $("#weight-output").value = `${event.currentTarget.value}%`;
    $("#weight-output").textContent = `${event.currentTarget.value}%`;
  });

  $("#result-filter").addEventListener("change", updateResultFilter);
  $("#export-csv").addEventListener("click", () => exportSavedRun("csv"));
  $("#export-json").addEventListener("click", () => exportSavedRun("json"));
  $("#refresh-history").addEventListener("click", () => {
    checkHealth();
    loadHistoryCount();
    if (!$("#history-view").hidden) loadHistory();
  });
  $("#history-reload").addEventListener("click", loadHistory);
  $("#export-parser-json").addEventListener("click", downloadParserResult);
  $("#history-body").addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-run]");
    if (button) openSavedRun(button.dataset.openRun);
  });

  $("#user-search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("#search-user-button");
    const byId = $("input[name='user-mode']:checked").value === "id";
    setBusy(button, true, "Ищу сообщения…");
    try {
      const result = await requestJson("/api/parser/user", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          username: $("#username-input").value.trim(),
          by_id: byId,
          max_pages: Number($("#user-max-pages").value || 1),
          timeout_ms: 3000,
        }),
      });
      renderParserResults(result);
      showToast(`Найдено сообщений: ${result.messages_count}.`, "success");
      if (result.warning) showToast(`Поиск остановлен по защитному лимиту: ${result.warning}`);
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setBusy(button, false);
    }
  });

  $$('input[name="user-mode"]').forEach((input) => {
    input.addEventListener("change", (event) => {
      const byId = event.currentTarget.value === "id";
      $("#username-label").textContent = byId ? "ID пользователя" : "Имя или ключевое слово";
      $("#username-input").placeholder = byId ? "Например, 12345" : "Например, имя автора";
    });
  });

  checkHealth();
  loadHistoryCount();
})();
