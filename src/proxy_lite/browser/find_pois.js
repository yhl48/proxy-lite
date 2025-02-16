marked_elements_convergence = [];

const interactiveTags = new Set([
    'a', 'button', 'details', 'embed', 'input', 'label',
    'menu', 'menuitem', 'object', 'select', 'textarea', 'summary',
    'video', 'audio', 'option', 'iframe'
]);

const interactiveRoles = new Set([
    'button', 'menu', 'menuitem', 'link', 'checkbox', 'radio',
    'slider', 'tab', 'tabpanel', 'textbox', 'combobox', 'grid',
    'listbox', 'option', 'progressbar', 'scrollbar', 'searchbox',
    'switch', 'tree', 'treeitem', 'spinbutton', 'tooltip',
    'a-button-inner', 'a-dropdown-button', 'click',
    'menuitemcheckbox', 'menuitemradio', 'a-button-text',
    'button-text', 'button-icon', 'button-icon-only',
    'button-text-icon-only', 'dropdown', 'combobox'
]);

findPOIsConvergence = (input = null) => {

    let rootElement = input ? input : document.documentElement;

    function isScrollable(element) {
        if ((input === null) && (element === document.documentElement)) {
            // we can always scroll the full page
            return false;
        }

        const style = window.getComputedStyle(element);

        const hasScrollableYContent = element.scrollHeight > element.clientHeight
        const overflowYScroll = style.overflowY === 'scroll' || style.overflowY === 'auto';

        const hasScrollableXContent = element.scrollWidth > element.clientWidth;
        const overflowXScroll = style.overflowX === 'scroll' || style.overflowX === 'auto';

        return (hasScrollableYContent && overflowYScroll) || (hasScrollableXContent && overflowXScroll);
    }

    function getEventListeners(element) {
        try {
            return window.getEventListeners?.(element) || {};
        } catch (e) {
            return {};
        }
    }

    function isInteractive(element) {
        if (!element) return false;

        return (hasInteractiveTag(element) ||
            hasInteractiveAttributes(element) ||
            hasInteractiveEventListeners(element)) ||
            isScrollable(element);
    }

    function hasInteractiveTag(element) {
        return interactiveTags.has(element.tagName.toLowerCase());
    }

    function hasInteractiveAttributes(element) {
        const role = element.getAttribute('role');
        const ariaRole = element.getAttribute('aria-role');
        const tabIndex = element.getAttribute('tabindex');
        const onAttribute = element.getAttribute('on');

        if (element.getAttribute('contenteditable') === 'true') return true;
        if ((role && interactiveRoles.has(role)) ||
            (ariaRole && interactiveRoles.has(ariaRole))) return true;
        if (tabIndex !== null && tabIndex !== '-1') return true;

        // Add check for AMP's 'on' attribute that starts with 'tap:'
        if (onAttribute && onAttribute.startsWith('tap:')) return true;

        const hasAriaProps = element.hasAttribute('aria-expanded') ||
            element.hasAttribute('aria-pressed') ||
            element.hasAttribute('aria-selected') ||
            element.hasAttribute('aria-checked');

        return hasAriaProps;
    }

    function hasInteractiveEventListeners(element) {
        const hasClickHandler = element.onclick !== null ||
             element.getAttribute('onclick') !== null ||
             element.hasAttribute('ng-click') ||
             element.hasAttribute('@click') ||
             element.hasAttribute('v-on:click');
        if (hasClickHandler) return true;

        const listeners = getEventListeners(element);
        return listeners && (
            listeners.click?.length > 0 ||
            listeners.mousedown?.length > 0 ||
            listeners.mouseup?.length > 0 ||
            listeners.touchstart?.length > 0 ||
            listeners.touchend?.length > 0
        );
    }

    function calculateArea(rects) {
        return rects.reduce((acc, rect) => acc + rect.width * rect.height, 0);
    }

    function getElementRects(element, context) {
        const vw = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
        const vh = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);

        let rects = [...element.getClientRects()];

        // If rects are empty (likely due to Shadow DOM), try to estimate position
        if (rects.length === 0 && element.getBoundingClientRect) {
            rects = [element.getBoundingClientRect()];
        }

        // Get iframe offset if element is in an iframe
        let iframeOffset = { x: 0, y: 0 };
        if (context !== document && context?.defaultView?.frameElement) {
            const iframe = context.defaultView.frameElement;
            if (iframe) {
                const iframeRect = iframe.getBoundingClientRect();
                iframeOffset = {
                    x: iframeRect.left,
                    y: iframeRect.top
                };
            }
        }

        return rects.filter(bb => {
            const center_x = bb.left + bb.width / 2 + iframeOffset.x;
            const center_y = bb.top + bb.height / 2 + iframeOffset.y;
            const elAtCenter = context.elementFromPoint(center_x - iframeOffset.x, center_y - iframeOffset.y);

            return elAtCenter === element || element.contains(elAtCenter);
        }).map(bb => {
            const rect = {
                left: Math.max(0, bb.left + iframeOffset.x),
                top: Math.max(0, bb.top + iframeOffset.y),
                right: Math.min(vw, bb.right + iframeOffset.x),
                bottom: Math.min(vh, bb.bottom + iframeOffset.y)
            };
            return {
                ...rect,
                width: rect.right - rect.left,
                height: rect.bottom - rect.top
            };
        });
    }

    function isElementVisible(element) {
        const style = window.getComputedStyle(element);
        return element.offsetWidth > 0 &&
            element.offsetHeight > 0 &&
            style.visibility !== 'hidden' &&
            style.display !== 'none';
    }

    function isTopElement(element) {
        let doc = element.ownerDocument;
        if (doc !== window.document) {
            // If in an iframe's document, treat as top
            return true;
        }
        const shadowRoot = element.getRootNode();
        if (shadowRoot instanceof ShadowRoot) {
            const rect = element.getBoundingClientRect();
            const point = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
            try {
                const topEl = shadowRoot.elementFromPoint(point.x, point.y);
                if (!topEl) return false;
                let current = topEl;
                while (current && current !== shadowRoot) {
                    if (current === element) return true;
                    current = current.parentElement;
                }
                return false;
            } catch (e) {
                return true;
            }
        }
        const rect = element.getBoundingClientRect();
        const point = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        try {
            const topEl = document.elementFromPoint(point.x, point.y);
            if (!topEl) return false;
            let current = topEl;
            while (current && current !== document.documentElement) {
                if (current === element) return true;
                current = current.parentElement;
            }
            return false;
        } catch (e) {
            return true;
        }
    }

    function getVisibleText(element, marked_elements_convergence = []) {
        const blockLikeDisplays = [
            // Basic block elements
            'block', 'flow-root', 'inline-block',
            // Lists
            'list-item',
            // Table elements
            'table', 'inline-table', 'table-row', 'table-cell',
            'table-caption', 'table-header-group', 'table-footer-group',
            'table-row-group',
            // Modern layouts
            'flex', 'inline-flex', 'grid', 'inline-grid'
        ];

        // Check if element is hidden
        const style = window.getComputedStyle(element);
        if (style.display === 'none' || style.visibility === 'hidden') {
            return '';
        }

        let collectedText = [];

        function isMarkedInteractive(el) {
            return marked_elements_convergence.includes(el);
        }

        function traverse(node) {
            if (
                node.nodeType === Node.ELEMENT_NODE &&
                node !== element &&
                isMarkedInteractive(node)
            ) {
                return false;
            }

            if (node.nodeType === Node.TEXT_NODE) {
                const trimmed = node.textContent.trim();
                if (trimmed) {
                    collectedText.push(trimmed);
                }
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                // Skip noscript elements
                if (node.tagName === 'NOSCRIPT') {
                    return true;
                }

                const nodeStyle = window.getComputedStyle(node);

                // Skip hidden elements
                if (nodeStyle.display === 'none' || nodeStyle.visibility === 'hidden') {
                    return true;
                }

                // Add newline before block elements if we have text
                if (blockLikeDisplays.includes(nodeStyle.display) && collectedText.length > 0) {
                    collectedText.push('\n');
                }

                if (node.tagName === 'IMG') {
                    const textParts = [];
                    const alt = node.getAttribute('alt');
                    const title = node.getAttribute('title');
                    const ariaLabel = node.getAttribute('aria-label');
                    // Add more as needed (e.g., 'aria-describedby', 'data-caption', etc.)

                    if (alt) textParts.push(`alt="${alt}"`);
                    if (title) textParts.push(`title="${title}"`);
                    if (ariaLabel) textParts.push(`aria-label="${ariaLabel}"`);

                    if (textParts.length > 0) {
                        collectedText.push(`[img - ${textParts.join(' ')}]`);
                    }
                    return true;
                }

                for (const child of node.childNodes) {
                    const shouldContinue = traverse(child);
                    if (shouldContinue === false) {
                        return false;
                    }
                }

                // Add newline after block elements
                if (blockLikeDisplays.includes(nodeStyle.display)) {
                    collectedText.push('\n');
                }
            }

            return true;
        }

        traverse(element);

        // Join text and normalize whitespace
        return collectedText.join(' ').trim().replace(/\s{2,}/g, ' ').trim();
    }

    function extractInteractiveItems(rootElement) {
        const items = [];

        function processElement(element, context) {
            if (!element) return;

            // Recursively process elements
            if (element.nodeType === Node.ELEMENT_NODE && isInteractive(element) && isElementVisible(element) && isTopElement(element)) {
                const rects = getElementRects(element, context);
                const area = calculateArea(rects);
                items.push({
                    element: element,
                    area,
                    rects,
                    is_scrollable: isScrollable(element),
                });
            }

            if (element.shadowRoot) {
                // if it's shadow DOM, process elements in the shadow DOM
                Array.from(element.shadowRoot.childNodes || []).forEach(child => {
                    processElement(child, element.shadowRoot);
                });
            }

            if (element.tagName === 'SLOT') {
                // Handle both assigned elements and nodes
                const assigned = element.assignedNodes ? element.assignedNodes() : element.assignedElements();
                assigned.forEach(child => {
                    processElement(child, context);
                });
            }
            else if (element.tagName === 'IFRAME') {
                try {
                    const iframeDoc = element.contentDocument || element.contentWindow?.document;
                    if (iframeDoc && iframeDoc.body) {
                        // Process elements inside iframe
                        processElement(iframeDoc.body, iframeDoc);
                    }
                } catch (e) {
                    console.warn('Unable to access iframe contents:', e);
                }
            } else {
                // if it's regular child elements, process regular child elements
                Array.from(element.children || []).forEach(child => {
                    processElement(child, context);
                });
            }
        }

        processElement(rootElement, document);
        return items;
    }

    if (marked_elements_convergence) {
        marked_elements_convergence = [];
    }
    let mark_centres = [];
    let marked_element_descriptions = [];
    var items = extractInteractiveItems(rootElement);

    // Lets create a floating border on top of these elements that will always be visible
    let index = 0;
    items.forEach(function (item) {
        item.rects.forEach((bbox) => {
            marked_elements_convergence.push(item.element);
            mark_centres.push({
                x: Math.round((bbox.left + bbox.right) / 2),
                y: Math.round((bbox.top + bbox.bottom) / 2),
                left: bbox.left,
                top: bbox.top,
                right: bbox.right,
                bottom: bbox.bottom,
            });
            marked_element_descriptions.push({
                tag: item.element.tagName,
                text: getVisibleText(item.element),
                // NOTE: all other attributes will be shown to the model when present
                // TODO: incorperate child attributes, e.g. <img alt="..."> when img is a child of the link element
                value: item.element.value,
                placeholder: item.element.getAttribute("placeholder"),
                element_type: item.element.getAttribute("type"),
                aria_label: item.element.getAttribute("aria-label"),
                name: item.element.getAttribute("name"),
                required: item.element.getAttribute("required"),
                disabled: item.element.getAttribute("disabled"),
                pattern: item.element.getAttribute("pattern"),
                checked: item.element.getAttribute("checked"),
                minlength: item.element.getAttribute("minlength"),
                maxlength: item.element.getAttribute("maxlength"),
                role: item.element.getAttribute("role"),
                title: item.element.getAttribute("title"),
                scrollable: item.is_scrollable
            });
            index++;
        });
    });

    return {
        element_descriptions: marked_element_descriptions,
        element_centroids: mark_centres
    };
}
