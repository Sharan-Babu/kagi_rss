// Visual selector logic
function computeSelector(el) {
    const field = window.pickerField;
    const itemSel = window.itemSelector;
    
    // For item_selector, return a generic selector that matches multiple elements
    if (field === 'item_selector') {
        return computeItemSelector(el);
    }
    
    // For other fields, try to make it relative to item container
    if (itemSel) {
        return computeRelativeSelector(el, itemSel);
    }
    
    // Fallback to generic selector
    return computeGenericSelector(el);
}

function computeItemSelector(el) {
    // Look for meaningful class names or tag patterns
    if (el.classList.length > 0) {
        for (let cls of el.classList) {
            if (cls.match(/(article|post|item|entry|card|story)/i)) {
                return '.' + cls;
            }
        }
        // Use first class if no semantic match
        return '.' + el.classList[0];
    }
    
    // Use tag name for semantic elements
    if (['article', 'section', 'div'].includes(el.tagName.toLowerCase())) {
        return el.tagName.toLowerCase();
    }
    
    return computeGenericSelector(el);
}

function computeRelativeSelector(el, itemSel) {
    const doc = el.ownerDocument;
    
    // Find the nearest ancestor that matches itemSel
    let container = el;
    while (container && container !== doc.body) {
        if (container.matches && container.matches(itemSel)) {
            break;
        }
        container = container.parentElement;
    }
    
    if (!container || container === doc.body) {
        // No container found, use generic approach
        return computeGenericSelector(el);
    }
    
    // Build path from container to element
    const path = [];
    let current = el;
    
    while (current && current !== container) {
        let selector = current.tagName.toLowerCase();
        
        // Add class if it looks semantic
        if (current.classList.length > 0) {
            const semanticClass = Array.from(current.classList).find(cls => 
                cls.match(/(title|content|image|img|date|author|link|text|description)/i)
            );
            if (semanticClass) {
                selector += '.' + semanticClass;
            } else {
                selector += '.' + current.classList[0];
            }
        }
        
        path.unshift(selector);
        current = current.parentElement;
    }
    
    return path.join(' ');
}

function computeGenericSelector(el) {
    if (el.id) return '#' + el.id;
    
    // For images, try to find a more generic pattern
    if (el.tagName.toLowerCase() === 'img') {
        // Look for semantic classes
        if (el.classList.length > 0) {
            const imgClass = Array.from(el.classList).find(cls => 
                cls.match(/(image|img|thumb|photo|picture|avatar)/i)
            );
            if (imgClass) return 'img.' + imgClass;
        }
        
        // Check parent for semantic context
        const parent = el.parentElement;
        if (parent && parent.classList.length > 0) {
            const parentClass = Array.from(parent.classList).find(cls => 
                cls.match(/(image|img|thumb|photo|picture|figure)/i)
            );
            if (parentClass) return '.' + parentClass + ' img';
        }
        
        return 'img';
    }
    
    // For other elements, prefer class-based selectors
    if (el.classList.length > 0) {
        return '.' + el.classList[0];
    }
    
    // Fallback to tag name
    return el.tagName.toLowerCase();
}

// Legacy function for backward compatibility
function computeSelectorOld(el) {
    const parts = [];
    while (el && el.nodeType === 1 && parts.length < 5 && el.tagName.toLowerCase() !== 'html') {
        let part = el.tagName.toLowerCase();
        if (el.classList.length > 0) {
            part += '.' + el.classList[0];
        }
        const siblings = Array.from(el.parentElement ? el.parentElement.children : []);
        const sameTag = siblings.filter(s => s.tagName === el.tagName);
        if (sameTag.length > 1) {
            const index = sameTag.indexOf(el) + 1;
            part += `:nth-of-type(${index})`;
        }
        parts.unshift(part);
        el = el.parentElement;
    }
    return parts.join(' > ');
}

document.addEventListener('DOMContentLoaded', () => {
    const iframe = document.getElementById('frame');
    iframe.addEventListener('load', () => {
        const doc = iframe.contentDocument || iframe.contentWindow.document;
        const highlightCls = '__highlight__';

        function clearHighlight() {
            doc.querySelectorAll('.' + highlightCls).forEach(e => e.classList.remove(highlightCls));
        }

        doc.addEventListener('mouseover', e => {
            clearHighlight();
            e.target.classList.add(highlightCls);
            e.stopPropagation();
        }, true);

        doc.addEventListener('mouseout', e => {
            e.target.classList.remove(highlightCls);
        }, true);

        doc.addEventListener('click', e => {
            e.preventDefault();
            e.stopPropagation();
            clearHighlight();
            const selector = computeSelector(e.target);
            if (window.opener) {
                window.opener.postMessage({field: window.pickerField, selector: selector}, '*');
            }
            window.close();
        }, true);
    });
}); 