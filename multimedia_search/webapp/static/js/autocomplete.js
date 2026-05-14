(function () {
    const input = document.getElementById("search-input");
    const form = document.getElementById("search-form");
    const box = document.getElementById("autocomplete-box");
    const list = document.getElementById("autocomplete-list");

    let debounceTimer = null;
    let activeIndex = -1;
    let currentItems = [];
    let activeController = null;
    const suggestionCache = new Map();

    function closeAutocomplete() {
        if (!box || !list) {
            return;
        }

        list.innerHTML = "";
        box.hidden = true;
        currentItems = [];
        activeIndex = -1;
    }

    function setActive(index) {
        const items = list.querySelectorAll(".autocomplete-item");

        items.forEach((item, i) => {
            item.classList.toggle("active", i === index);
        });

        activeIndex = index;
    }

    function chooseSuggestion(value) {
        input.value = value;
        closeAutocomplete();
        form.submit();
    }

    function renderSuggestions(items) {
        currentItems = items || [];
        list.innerHTML = "";

        if (!currentItems.length) {
            closeAutocomplete();
            return;
        }

        currentItems.forEach((value, index) => {
            const li = document.createElement("li");
            li.className = "autocomplete-item";
            li.setAttribute("data-value", value);

            li.innerHTML = `
                <span class="autocomplete-item-icon">⌕</span>
                <span class="autocomplete-item-text"></span>
            `;

            li.querySelector(".autocomplete-item-text").textContent = value;

            li.addEventListener("mousedown", function (event) {
                event.preventDefault();
                chooseSuggestion(value);
            });

            li.addEventListener("mouseenter", function () {
                setActive(index);
            });

            list.appendChild(li);
        });

        box.hidden = false;
        activeIndex = -1;
    }

    async function fetchSuggestions(query) {
        const normalizedQuery = query.trim().toLowerCase();

        if (suggestionCache.has(normalizedQuery)) {
            renderSuggestions(suggestionCache.get(normalizedQuery));
            return;
        }

        if (activeController) {
            activeController.abort();
        }

        activeController = new AbortController();

        try {
            const response = await fetch(
                `/autocomplete?q=${encodeURIComponent(query)}`,
                { signal: activeController.signal }
            );

            if (!response.ok) {
                closeAutocomplete();
                return;
            }

            const data = await response.json();
            const suggestions = data.suggestions || [];

            suggestionCache.set(normalizedQuery, suggestions);
            renderSuggestions(suggestions);
        } catch (error) {
            if (error.name !== "AbortError") {
                closeAutocomplete();
            }
        }
    }

    function setupAutocomplete() {
        if (!input || !form || !box || !list) {
            return;
        }

        input.addEventListener("input", function () {
            const value = input.value.trim();

            clearTimeout(debounceTimer);

            if (!value) {
                closeAutocomplete();
                return;
            }

            debounceTimer = setTimeout(function () {
                fetchSuggestions(value);
            }, 120);
        });

        input.addEventListener("keydown", function (event) {
            const items = list.querySelectorAll(".autocomplete-item");

            if (box.hidden || !items.length) {
                return;
            }

            if (event.key === "ArrowDown") {
                event.preventDefault();
                const next = activeIndex < items.length - 1 ? activeIndex + 1 : 0;
                setActive(next);
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                const next = activeIndex > 0 ? activeIndex - 1 : items.length - 1;
                setActive(next);
            } else if (event.key === "Enter") {
                if (activeIndex >= 0 && activeIndex < currentItems.length) {
                    event.preventDefault();
                    chooseSuggestion(currentItems[activeIndex]);
                }
            } else if (event.key === "Escape") {
                closeAutocomplete();
            }
        });

        document.addEventListener("click", function (event) {
            if (!box.contains(event.target) && event.target !== input) {
                closeAutocomplete();
            }
        });

        window.addEventListener("keydown", function (event) {
            const isTypingTarget =
                event.target instanceof HTMLInputElement ||
                event.target instanceof HTMLTextAreaElement ||
                event.target instanceof HTMLSelectElement;

            if (event.key === "/" && !isTypingTarget) {
                event.preventDefault();
                input.focus();
            }
        });
    }

    function preserveClickedSubmitAction() {
        document.addEventListener(
            "submit",
            function (event) {
                const formElement = event.target;
                const submitter = event.submitter;

                if (!formElement || !submitter) {
                    return;
                }

                if (formElement.dataset.dynamicForm === "1") {
                    return;
                }

                if (!submitter.name || !submitter.value) {
                    return;
                }

                const existing = formElement.querySelector(
                    'input[type="hidden"][data-preserved-submit-action="1"]'
                );

                if (existing) {
                    existing.remove();
                }

                const hidden = document.createElement("input");
                hidden.type = "hidden";
                hidden.name = submitter.name;
                hidden.value = submitter.value;
                hidden.setAttribute("data-preserved-submit-action", "1");

                formElement.appendChild(hidden);
            },
            true
        );
    }

    function getFormFingerprint(formElement) {
        const formData = new FormData(formElement);
        const parts = [];

        for (const [key, value] of formData.entries()) {
            if (value instanceof File) {
                parts.push(`${key}:${value.name}:${value.size}`);
            } else {
                parts.push(`${key}:${String(value).trim()}`);
            }
        }

        return parts.sort().join("|");
    }

    function setupSubmitGuards() {
        const forms = document.querySelectorAll("form");

        forms.forEach((formElement) => {
            if (formElement.dataset.dynamicForm === "1") {
                return;
            }

            formElement.addEventListener("submit", function (event) {
                const submitButton =
                    event.submitter ||
                    formElement.querySelector("button[type='submit'], button:not([type])");

                const fingerprint = getFormFingerprint(formElement);
                const now = Date.now();
                const lastRaw = sessionStorage.getItem("lastFormSubmit");

                if (lastRaw) {
                    try {
                        const last = JSON.parse(lastRaw);

                        if (last.fingerprint === fingerprint && now - last.time < 1500) {
                            event.preventDefault();
                            return;
                        }
                    } catch (_error) {
                        sessionStorage.removeItem("lastFormSubmit");
                    }
                }

                sessionStorage.setItem(
                    "lastFormSubmit",
                    JSON.stringify({
                        fingerprint,
                        time: now,
                    })
                );

                if (submitButton) {
                    submitButton.dataset.originalText = submitButton.textContent;
                    submitButton.disabled = true;
                    submitButton.textContent = "Working...";
                }
            });
        });
    }

    function setupToastPopup() {
        const toast = document.getElementById("toast-popup");

        if (!toast) {
            return;
        }

        const closeButton = toast.querySelector(".toast-close");

        function closeToast() {
            toast.classList.add("toast-hide");

            window.setTimeout(function () {
                toast.remove();
            }, 220);
        }

        if (closeButton) {
            closeButton.addEventListener("click", closeToast);
        }

        window.setTimeout(closeToast, 4500);
    }

    function setupConfirmDialogs() {
        document.addEventListener(
            "submit",
            function (event) {
                const formElement = event.target;
                const submitter = event.submitter;

                if (!formElement || !submitter) {
                    return;
                }

                const message = submitter.getAttribute("data-confirm-message");

                if (!message) {
                    return;
                }

                const confirmed = window.confirm(message);

                if (!confirmed) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                }
            },
            true
        );
    }

    function setupQueryImageInputs() {
        const pathInput = document.getElementById("similar_image_path");
        const fileInput = document.getElementById("similar_image_file");
        const previewBox = document.getElementById("query-image-preview");
        const previewImg = document.getElementById("query-image-preview-img");
        const clearButton = document.getElementById("clear-query-image");

        if (!pathInput || !fileInput) {
            return;
        }

        let objectUrl = null;

        function clearPreview() {
            if (objectUrl) {
                URL.revokeObjectURL(objectUrl);
                objectUrl = null;
            }

            if (previewImg) {
                previewImg.removeAttribute("src");
            }

            if (previewBox) {
                previewBox.hidden = true;
            }
        }

        function showPreview(file) {
            clearPreview();

            if (!file || !previewBox || !previewImg) {
                return;
            }

            objectUrl = URL.createObjectURL(file);
            previewImg.src = objectUrl;
            previewBox.hidden = false;
        }

        fileInput.addEventListener("change", function () {
            if (fileInput.files && fileInput.files.length > 0) {
                pathInput.value = "";
                showPreview(fileInput.files[0]);
            } else {
                clearPreview();
            }
        });

        pathInput.addEventListener("input", function () {
            if (pathInput.value.trim() && fileInput.value) {
                fileInput.value = "";
                clearPreview();
            }
        });

        if (clearButton) {
            clearButton.addEventListener("click", function () {
                fileInput.value = "";
                clearPreview();
            });
        }

        window.addEventListener("beforeunload", clearPreview);
    }

    function setupAudioTranscriptToggles() {
        const buttons = document.querySelectorAll(".audio-transcript-toggle");

        buttons.forEach((button) => {
            button.addEventListener("click", function () {
                const block = button.closest(".audio-transcript-block");

                if (!block) {
                    return;
                }

                const transcript = block.querySelector(".audio-transcript-text");

                if (!transcript) {
                    return;
                }

                const isHidden = transcript.hidden;
                transcript.hidden = !isHidden;
                button.setAttribute("aria-expanded", String(isHidden));
                button.textContent = isHidden ? "Hide full transcript" : "See full transcript";
            });
        });
    }

    function escapeHtml(value) {
        return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function getLinesFromTextarea(id) {
        const textarea = document.getElementById(id);

        if (!textarea) {
            return [];
        }

        return textarea.value
            .split(/\r?\n/)
            .map((line) => line.trim())
            .filter(Boolean);
    }

    function setImportStatus(message, type = "working") {
        const statusBox = document.getElementById("externalImportStatus");

        if (!statusBox) {
            return;
        }

        statusBox.textContent = message;
        statusBox.className = `web-live-status ${type}`;
    }

    function renderSimpleImportResult(title, ok, message) {
        const resultsBox = document.getElementById("externalImportResults");

        if (!resultsBox) {
            return;
        }

        const status = ok ? "Imported" : "Failed";

        resultsBox.innerHTML = `
            <article class="web-live-result">
                <div class="result-topline">
                    <span class="result-badge">${escapeHtml(status)}</span>
                </div>
                <h3>${escapeHtml(title)}</h3>
                <p class="result-snippet">${escapeHtml(message || "")}</p>
            </article>
        `;
    }

    function setupExternalImport() {
        const form = document.getElementById("externalImportForm");
        const topicsInput = document.getElementById("externalImportTopics");
        const limitInput = document.getElementById("externalImportLimit");
        const platformInput = document.getElementById("shortVideoPlatform");
        const youtubeFeedsInput = document.getElementById("youtubeRssFeeds");
        const statusBox = document.getElementById("externalImportStatus");
        const resultsBox = document.getElementById("externalImportResults");
    
        if (!form || !topicsInput || !limitInput || !platformInput || !youtubeFeedsInput || !statusBox || !resultsBox) {
            return;
        }
    
        function getLines(inputElement) {
            return inputElement.value
                .split(/\r?\n/)
                .map((line) => line.trim())
                .filter(Boolean);
        }
    
        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            event.stopImmediatePropagation();
    
            const topics = getLines(topicsInput);
            const youtubeRssFeeds = getLines(youtubeFeedsInput);
            const limit = Number(limitInput.value || 10);
            const shortVideoPlatform = platformInput.value || "none";
    
            if (!topics.length) {
                statusBox.textContent = "Please enter at least one topic.";
                statusBox.className = "web-live-status error";
                return;
            }
    
            if (shortVideoPlatform === "youtube_rss" && youtubeRssFeeds.length === 0) {
                statusBox.textContent = "Please enter at least one YouTube channel RSS feed URL.";
                statusBox.className = "web-live-status error";
                return;
            }
    
            const button = form.querySelector("button[type='submit']");
            const oldText = button ? button.textContent : "Import Data";
    
            if (button) {
                button.disabled = true;
                button.textContent = "Importing...";
            }
    
            statusBox.textContent = "Importing documents, images, audio, videos, news, and short-video metadata...";
            statusBox.className = "web-live-status working";
            resultsBox.innerHTML = "";
    
            try {
                const response = await fetch("/api/import/smart", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    body: JSON.stringify({
                        topics: topics,
                        limit: limit,
                        short_video_platform: shortVideoPlatform,
                        youtube_rss_feeds: youtubeRssFeeds,
                    }),
                });
    
                const payload = await response.json();
    
                if (!response.ok || !payload.ok) {
                    statusBox.textContent = payload.error || payload.message || "Import failed.";
                    statusBox.className = "web-live-status error";
                    return;
                }
    
                const details = payload.metadata && payload.metadata.details
                    ? payload.metadata.details
                    : [];
    
                resultsBox.innerHTML = details.map((item) => {
                    return `
                        <article class="web-live-result">
                            <div class="result-topline">
                                <span class="result-badge">Imported</span>
                            </div>
                            <h3>${escapeHtml(item.topic || "Topic")}</h3>
                            <p class="result-snippet">
                                Wikipedia: ${item.wikipedia || 0},
                                Images: ${item.openverse_images || 0},
                                Audio: ${item.openverse_audio || 0},
                                Videos: ${item.internet_archive_videos || 0},
                                News: ${item.gdelt_news || 0},
                                Short videos: ${(item.topic_short_videos || 0) + (item.youtube_rss_short_videos || 0)}
                            </p>
                        </article>
                    `;
                }).join("");
    
                statusBox.textContent = `Done. Imported ${payload.imported_count || 0} new item(s). Refresh the page to update stats.`;
                statusBox.className = "web-live-status success";
            } catch (error) {
                statusBox.textContent = `Import failed: ${error.message || error}`;
                statusBox.className = "web-live-status error";
            } finally {
                if (button) {
                    button.disabled = false;
                    button.textContent = oldText;
                }
            }
        }, true);
    }

    function renderExternalImportLogs(logs) {
        const resultsBox = document.getElementById("externalImportResults");

        if (!resultsBox) {
            return;
        }

        resultsBox.innerHTML = logs.map((item) => {
            const status = item.ok ? "Imported" : "Failed";
            const count = item.ok ? `${item.imported} item(s)` : escapeHtml(item.error || "");

            return `
                <article class="web-live-result">
                    <div class="result-topline">
                        <span class="result-badge">${escapeHtml(status)}</span>
                    </div>
                    <h3>${escapeHtml(item.topic)}</h3>
                    <p class="result-snippet">${count}</p>
                </article>
            `;
        }).join("");
    }

    function setupWebUrlImport() {
        const form = document.getElementById("webUrlImportForm");

        if (!form) {
            return;
        }

        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            event.stopImmediatePropagation();

            const urls = getLinesFromTextarea("webImportUrls");

            if (!urls.length) {
                setImportStatus("Please enter at least one web URL.", "error");
                return;
            }

            const button = form.querySelector("button[type='submit']");
            const oldText = button ? button.textContent : "Import Web URLs";

            if (button) {
                button.disabled = true;
                button.textContent = "Importing...";
            }

            setImportStatus("Importing web URLs...", "working");

            try {
                const response = await fetch("/api/index/web", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    body: JSON.stringify({ urls: urls })
                });

                const payload = await response.json();

                if (!response.ok || !payload.ok) {
                    setImportStatus(payload.error || payload.message || "Web import failed.", "error");
                    renderSimpleImportResult("Web URL import", false, payload.error || payload.message || "Failed");
                    return;
                }

                setImportStatus(`Done. Imported ${payload.indexed_count || 0} web page(s). Refresh the page to update stats.`, "success");
                renderSimpleImportResult("Web URL import", true, payload.message || "Done.");
            } catch (error) {
                setImportStatus(`Web import failed: ${error.message || error}`, "error");
            } finally {
                if (button) {
                    button.disabled = false;
                    button.textContent = oldText;
                }
            }
        }, true);
    }

    function setupNewsImport() {
        const form = document.getElementById("newsImportForm");

        if (!form) {
            return;
        }

        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            event.stopImmediatePropagation();

            const feedUrls = getLinesFromTextarea("newsFeedUrls");
            const limitInput = document.getElementById("newsImportLimit");
            const limit = Number(limitInput ? limitInput.value : 10) || 10;

            if (!feedUrls.length) {
                setImportStatus("Please enter at least one RSS feed URL.", "error");
                return;
            }

            const button = form.querySelector("button[type='submit']");
            const oldText = button ? button.textContent : "Import News";

            if (button) {
                button.disabled = true;
                button.textContent = "Importing...";
            }

            setImportStatus("Importing news RSS...", "working");

            try {
                const response = await fetch("/api/import/news", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    body: JSON.stringify({
                        feed_urls: feedUrls,
                        limit: limit
                    })
                });

                const payload = await response.json();

                if (!response.ok || !payload.ok) {
                    setImportStatus(payload.error || payload.message || "News import failed.", "error");
                    renderSimpleImportResult("News RSS import", false, payload.error || payload.message || "Failed");
                    return;
                }

                setImportStatus(`Done. Imported ${payload.imported_count || 0} news article(s). Refresh the page to update stats.`, "success");
                renderSimpleImportResult("News RSS import", true, payload.message || "Done.");
            } catch (error) {
                setImportStatus(`News import failed: ${error.message || error}`, "error");
            } finally {
                if (button) {
                    button.disabled = false;
                    button.textContent = oldText;
                }
            }
        }, true);
    }

    function setupShortVideoImport() {
        const form = document.getElementById("shortVideoImportForm");

        if (!form) {
            return;
        }

        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            event.stopImmediatePropagation();

            const platformInput = document.getElementById("shortVideoPlatform");
            const jsonInput = document.getElementById("shortVideoItems");

            const platform = platformInput ? platformInput.value.trim() : "";
            const rawJson = jsonInput ? jsonInput.value.trim() : "";

            if (!rawJson) {
                setImportStatus("Please paste short-video metadata JSON.", "error");
                return;
            }

            let items = [];

            try {
                const parsed = JSON.parse(rawJson);

                if (Array.isArray(parsed)) {
                    items = parsed;
                } else if (parsed && typeof parsed === "object") {
                    items = [parsed];
                }
            } catch (error) {
                setImportStatus(`Invalid JSON: ${error.message || error}`, "error");
                return;
            }

            if (!items.length) {
                setImportStatus("Short-video JSON must contain at least one item.", "error");
                return;
            }

            const button = form.querySelector("button[type='submit']");
            const oldText = button ? button.textContent : "Import Short Videos";

            if (button) {
                button.disabled = true;
                button.textContent = "Importing...";
            }

            setImportStatus("Importing short-video metadata...", "working");

            try {
                const response = await fetch("/api/import/short-videos", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    body: JSON.stringify({
                        platform: platform,
                        items: items
                    })
                });

                const payload = await response.json();

                if (!response.ok || !payload.ok) {
                    setImportStatus(payload.error || payload.message || "Short-video import failed.", "error");
                    renderSimpleImportResult("Short-video import", false, payload.error || payload.message || "Failed");
                    return;
                }

                setImportStatus(`Done. Imported ${payload.imported_count || 0} short-video item(s). Refresh the page to update stats.`, "success");
                renderSimpleImportResult("Short-video import", true, payload.message || "Done.");
            } catch (error) {
                setImportStatus(`Short-video import failed: ${error.message || error}`, "error");
            } finally {
                if (button) {
                    button.disabled = false;
                    button.textContent = oldText;
                }
            }
        }, true);
    }

    preserveClickedSubmitAction();
    setupAutocomplete();
    setupConfirmDialogs();
    setupSubmitGuards();
    setupQueryImageInputs();
    setupAudioTranscriptToggles();
    setupToastPopup();
    setupExternalImport();
})();