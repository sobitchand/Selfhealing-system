"""
Universal DOM Mutator — breaks elements on ANY live web page.

Instead of using a pre-made "broken HTML" file, this injects JavaScript into the
browser that renames IDs, classes, and attributes of interactive elements. This
works on any real website, not just our demo app.

Usage:
    from dom_mutator import mutate_page
    mutate_page(driver)  # breaks elements on the current page
"""

import json
import random

# JavaScript that renames IDs and classes of interactive elements on the current page.
# Returns a map of {old_id: new_id, old_class: new_class} so the test runner knows
# what was changed.
_MUTATE_JS = """
(function() {
    var changes = [];
    var interactive = document.querySelectorAll('button, a, input, select, textarea, [onclick]');

    function randSuffix() {
        return '_' + Math.random().toString(36).substring(2, 8);
    }

    interactive.forEach(function(el) {
        // Rename ID
        var oldId = el.id;
        if (oldId) {
            var newId = oldId + randSuffix();
            el.id = newId;
            changes.push({type: 'id', old: oldId, new: newId, tag: el.tagName.toLowerCase()});
        }

        // Rename class
        var oldClass = el.className;
        if (oldClass && typeof oldClass === 'string') {
            var newClass = oldClass + ' ' + 'mutated' + randSuffix();
            el.className = newClass;
            changes.push({type: 'class', old: oldClass, new: newClass, tag: el.tagName.toLowerCase()});
        }

        // Rename data attributes
        var attrs = el.attributes;
        for (var i = 0; i < attrs.length; i++) {
            var attr = attrs[i];
            if (attr.name.startsWith('data-') && !attr.name.includes('mutated')) {
                var newAttrName = attr.name + '-mutated';
                el.setAttribute(newAttrName, attr.value);
                el.removeAttribute(attr.name);
                changes.push({type: 'attr', old: attr.name, new: newAttrName, tag: el.tagName.toLowerCase()});
            }
        }
    });

    return JSON.stringify(changes);
})();
"""


def mutate_page(driver):
    """
    Inject JavaScript into the current page to rename IDs, classes, and data attributes
    of all interactive elements. Returns a list of changes made.

    Works on ANY web page - no hardcoded elements needed.
    """
    result = driver.execute_script(_MUTATE_JS)
    try:
        changes = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        changes = []

    print(f"Mutated {len(changes)} elements on page:")
    for change in changes[:10]:  # Show first 10
        print(f"  {change['tag']}: {change['old']} -> {change['new']}")
    if len(changes) > 10:
        print(f"  ... and {len(changes) - 10} more")

    return changes


def mutate_specific_element(driver, old_id, new_id):
    """Rename a specific element's ID. Useful for targeted breakage."""
    js = f"""
    (function() {{
        var el = document.getElementById('{old_id}');
        if (el) {{
            el.id = '{new_id}';
            return 'renamed {old_id} to {new_id}';
        }}
        return 'element not found: {old_id}';
    }})();
    """
    result = driver.execute_script(js)
    print(f"  {result}")
    return result
