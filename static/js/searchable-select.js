/*
 * Adds a filter box above any <select data-searchable>, so long option lists
 * such as the course catalogue can be narrowed by typing. Without JavaScript
 * the select works exactly as before.
 */
(function () {
    function enhance(select) {
        if (select.dataset.searchReady) {
            return;
        }
        select.dataset.searchReady = "true";

        var search = document.createElement("input");
        search.type = "search";
        search.className = "select-search";
        search.placeholder = select.dataset.searchPlaceholder || "Search options";
        search.setAttribute("aria-label", search.placeholder);
        select.parentNode.insertBefore(search, select);

        var options = Array.prototype.slice.call(select.options);

        function applyFilter() {
            var term = search.value.trim().toLowerCase();
            options.forEach(function (option) {
                var matches = !term || option.text.toLowerCase().indexOf(term) !== -1;
                // Keep the current choice visible so the field never looks blank.
                if (option.selected && option.value !== "") {
                    matches = true;
                }
                option.hidden = !matches;
                option.disabled = !matches;
                option.style.display = matches ? "" : "none";
            });
        }

        search.addEventListener("input", applyFilter);
        search.addEventListener("search", applyFilter);
        select.addEventListener("change", function () {
            // A new choice may have been outside the filter; show the full list again.
            if (search.value) {
                search.value = "";
                applyFilter();
            }
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("select[data-searchable]").forEach(enhance);
    });
})();
