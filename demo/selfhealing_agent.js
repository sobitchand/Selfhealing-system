(function () {
  console.log("🛡️ Rule-Based Self-Healing Browser Agent initialized and guarding active DOM view.");

  const config = window.SELF_HEALING_CONFIG || {
    appName: "Generic Static Web Target",
    collectorUrl: "http://127.0.0.1:8766/selfhealing/events",
    fallbackImage: "https://placehold.co/600x400?text=Asset+Unavailable",
    watchSelectors: []
  };

  // Helper utility to forward payloads to the backend collector
  async function transmitEvent(payload) {
    try {
      payload.appName = config.appName;
      await fetch(config.collectorUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    } catch (err) {
      console.error("⚠️ Self-Healing Collector server unreachable:", err.message);
    }
  }

  // Layer A: Intercept unhandled JavaScript errors and exceptions on the page
  window.addEventListener("error", function (event) {
    if (event.filename && event.filename.includes("selfhealing_agent.js")) return;

    transmitEvent({
      type: "js_error",
      message: event.message || "Unhandled script execution crash",
      file: event.filename || "unknown_module",
      line: event.lineno || 0
    });
  }, true);

  // Layer B: Automatically heal broken images by applying clean placeholders
  window.addEventListener("error", function (event) {
    const targetElement = event.target;
    if (targetElement && targetElement.tagName === "IMG") {
      console.warn("🖼️ Broken resource asset detected. Applying image fallback fix...");
      
      transmitEvent({
        type: "resource_failure",
        message: `Failed to load asset source location: ${targetElement.src}`
      });

      if (config.fallbackImage && targetElement.src !== config.fallbackImage) {
        targetElement.src = config.fallbackImage;
      }
    }
  }, true);

  // Layer C: Fallback selector recovery loop execution
  document.addEventListener("DOMContentLoaded", function () {
    if (!config.watchSelectors || config.watchSelectors.length === 0) return;

    config.watchSelectors.forEach(item => {
      const standardElement = document.querySelector(item.selector);
      
      // If the primary locator is broken, begin dynamic recovery search
      if (!standardElement) {
        console.warn(`🔗 Target selector missing: [${item.selector}]. Running browser heuristic search...`);
        
        const possibleElements = document.querySelectorAll(item.fallbackSelector || "button, a");
        let matchedTarget = null;

        for (let el of possibleElements) {
          // Compare the dynamic element text against our saved fingerprint data
          if (item.fingerprint && el.textContent.trim().toLowerCase() === item.fingerprint.text.toLowerCase()) {
            matchedTarget = el;
            break;
          }
        }

        if (matchedTarget) {
          console.log(`✨ Alternative path found for "${item.name}". Re-mapping references...`);
          
          // Apply a fallback structural class name directly in the browser DOM to restore functionality
          if (item.fingerprint && item.fingerprint.className) {
             matchedTarget.className = item.fingerprint.className;
          }

          transmitEvent({
            type: "selector_recovery",
            brokenSelector: item.selector,
            recoveredSelector: `${matchedTarget.tagName.toLowerCase()}[text='${matchedTarget.textContent.trim()}']`,
            confidence: 88.5,
            resolved: true
          });
        } else {
          transmitEvent({
            type: "selector_recovery",
            brokenSelector: item.selector,
            recoveredSelector: "none",
            confidence: 0.0,
            resolved: false
          });
        }
      }
    });
  });
})();