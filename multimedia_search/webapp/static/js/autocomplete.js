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
    preserveClickedSubmitAction();
    setupAutocomplete();
    setupSubmitGuards();
    setupQueryImageInputs();
    setupAudioTranscriptToggles();
    setupToastPopup();
})();