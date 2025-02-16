handledSelectElementsConvergence = new WeakSet();

overwriteDefaultSelectConvergence = (input = null) => {
    let activeSelectElement = null;

    // Handle iframe input element
    let rootElement = input ? input : document.documentElement;

    function createCustomSelectElement() {
        // Create the custom select container
        const customSelect = document.createElement('div');
        customSelect.id = 'convergence-custom-select-element-X2EmudtLRN';
        customSelect.style.position = 'absolute'
        customSelect.style.zIndex = 2147483647 - 1;
        customSelect.style.display = 'none';
        document.body.appendChild(customSelect);

        // Create the select options list
        const optionsList = document.createElement('div');
        optionsList.style.border = '1px solid #ccc';
        optionsList.style.backgroundColor = '#fff';
        optionsList.style.color = 'black';
        customSelect.appendChild(optionsList);

        return customSelect;
    }

    function showCustomSelect(select) {
        activeSelectElement = select;

        // Clear previous options
        const customSelect = rootElement.querySelector('#convergence-custom-select-element-X2EmudtLRN');
        let optionsList = customSelect.firstChild;
        optionsList.innerHTML = '';

        // Populate with new options
        Array.from(select.options).forEach(option => {
            const customOption = document.createElement('div');
            customOption.className = 'custom-option';
            customOption.style.padding = '8px';
            customOption.style.cursor = 'pointer';
            customOption.textContent = option.text;
            customOption.dataset.value = option.value;
            optionsList.appendChild(customOption);

            customOption.addEventListener('mouseenter', function () {
                customOption.style.backgroundColor = '#f0f0f0';
            });

            customOption.addEventListener('mouseleave', function () {
                customOption.style.backgroundColor = '';
            });

            customOption.addEventListener('mousedown', (e) => {
                e.stopPropagation();
                select.value = customOption.dataset.value;
                customSelect.style.display = 'none';
                activeSelectElement = null;
                // ensure we trigger all potential event listeners
                select.dispatchEvent(new InputEvent('focus', { bubbles: true, cancelable: true }));
                select.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true }));
                select.dispatchEvent(new InputEvent('change', { bubbles: true, cancelable: true }));
                select.dispatchEvent(new InputEvent('blur', { bubbles: true, cancelable: true }));
            });
        });

        // Position and show the custom select
        const selectRect = select.getBoundingClientRect();
        customSelect.style.top = `${selectRect.bottom + window.scrollY}px`;
        customSelect.style.left = `${selectRect.left + window.scrollX}px`;
        customSelect.style.width = `${selectRect.width}px`;
        customSelect.style.display = 'block';
        select.focus();
        select.addEventListener('blur', function (e) {
            customSelect.style.display = 'none';
            activeSelectElement = null;
        });
        select.addEventListener('change', function (e) {
            customSelect.style.display = 'none';
            activeSelectElement = null;
        });
    }

    // Ensure we have a custom select element
    let customSelect = rootElement.querySelector(`#convergence-custom-select-element-X2EmudtLRN`);
    if (!customSelect) {
        customSelect = createCustomSelectElement();
    }

    // Find selects in shadow DOMs
    function findSelectInShadowRoot(element) {
        if (element.shadowRoot) {
            return element.shadowRoot.querySelectorAll('select');
        }
        return [];
    }
    let shadowSelects = [];
    rootElement.querySelectorAll('*').forEach(el => {
        shadowSelects.push(...findSelectInShadowRoot(el));
    });

    // Find selects in the regular (light) DOM
    const lightSelects = Array.from(rootElement.querySelectorAll('select'));

    // Add event listeners to all select elements
    const allSelects = [...lightSelects, ...shadowSelects];
    allSelects.forEach(select => {
        if (select.hasAttribute('multiple')) {
            // skip special multiple elements as our POI code already handles them
            return;
        }
        if (!handledSelectElementsConvergence.has(select)) {
            select.addEventListener('mousedown', (e) => {
                // only use custom select when the default behaviour is being used
                if (!e.defaultPrevented) {
                    showCustomSelect(select);
                    e.preventDefault();
                }
            });
            handledSelectElementsConvergence.add(select);
        }
    });
}
