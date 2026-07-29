"""
Advanced Analytics — Features that beat Healenium and Testim.

1. Locator Stability Scoring
   - Predicts which locators are likely to break based on their attributes
   - Scores locators on: specificity, uniqueness, semantic meaning, DOM depth
   - Recommends better locators when stability is low

2. Flaky Test Detection
   - Tracks heal frequency per test/locator
   - Identifies tests that heal repeatedly (likely flaky)
   - Suggests refactoring or locator improvement

3. Heal Cost Analysis
   - Calculates time saved vs manual fixing
   - Estimates ROI of the self-healing system
   - Tracks cumulative savings over time

These features provide insights that neither Healenium nor Testim offer.
"""

import json
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import config
import store


class LocatorStabilityAnalyzer:
    """Analyze locator stability and predict breakage likelihood."""
    
    # Stability scoring weights
    WEIGHTS = {
        "id_specificity": 30,        # IDs are most stable
        "semantic_meaning": 25,      # Semantic names (start-btn) > generic (btn-123)
        "uniqueness": 20,            # Unique locators are more stable
        "dom_depth": 15,             # Shallow DOM = more stable
        "text_content": 10,          # Visible text is stable
    }
    
    # Patterns that indicate unstable locators
    UNSTABLE_PATTERNS = [
        r"\d+",                      # Numeric suffixes (btn-123)
        r"generated|auto|temp",      # Auto-generated names
        r"^\w{1,2}$",                # Very short names (a, b1)
        r"ng-|react-|vue-",          # Framework-specific prefixes
    ]
    
    # Patterns that indicate stable locators
    STABLE_PATTERNS = [
        r"start|stop|reset|submit",  # Action words
        r"btn|button|link",          # Element type
        r"user|email|password",      # Domain-specific
        r"nav|menu|header|footer",   # Structural
    ]
    
    def analyze_locator(self, locator_by, locator_value, driver=None):
        """Score a locator's stability (0-100, higher = more stable)."""
        score = 0
        reasons = []
        
        # ID specificity (30 points)
        if locator_by == "id":
            score += 30
            reasons.append("ID-based locator (most stable)")
        elif locator_by == "css selector" and locator_value.startswith("#"):
            score += 25
            reasons.append("CSS ID selector (very stable)")
        elif locator_by == "xpath" and "@id=" in locator_value:
            score += 20
            reasons.append("XPath with ID (stable)")
        else:
            score += 5
            reasons.append("Non-ID locator (less stable)")
        
        # Semantic meaning (25 points)
        value_lower = str(locator_value).lower()
        has_stable = any(re.search(p, value_lower) for p in self.STABLE_PATTERNS)
        has_unstable = any(re.search(p, value_lower) for p in self.UNSTABLE_PATTERNS)
        
        if has_stable and not has_unstable:
            score += 25
            reasons.append("Semantic, meaningful name")
        elif has_stable and has_unstable:
            score += 15
            reasons.append("Mixed stability signals")
        elif has_unstable:
            score += 5
            reasons.append("Auto-generated or numeric pattern")
        else:
            score += 10
            reasons.append("Neutral naming")
        
        # Uniqueness (20 points) - would need driver to check
        if driver:
            try:
                from selenium.webdriver.common.by import By
                by_map = {
                    "id": By.ID,
                    "css selector": By.CSS_SELECTOR,
                    "xpath": By.XPATH,
                    "class name": By.CLASS_NAME,
                }
                selenium_by = by_map.get(locator_by, By.ID)
                elements = driver.find_elements(selenium_by, locator_value)
                if len(elements) == 1:
                    score += 20
                    reasons.append("Unique match (1 element)")
                elif len(elements) <= 3:
                    score += 10
                    reasons.append(f"Few matches ({len(elements)} elements)")
                else:
                    score += 0
                    reasons.append(f"Many matches ({len(elements)} elements)")
            except Exception:
                score += 10
                reasons.append("Uniqueness check failed")
        else:
            score += 10
            reasons.append("Uniqueness not checked (no driver)")
        
        # DOM depth (15 points) - for XPath
        if locator_by == "xpath":
            depth = locator_value.count("/")
            if depth <= 3:
                score += 15
                reasons.append("Shallow XPath (stable)")
            elif depth <= 5:
                score += 10
                reasons.append("Medium depth XPath")
            else:
                score += 5
                reasons.append("Deep XPath (fragile)")
        else:
            score += 10
            reasons.append("Non-XPath (depth N/A)")
        
        # Text content (10 points) - for XPath with text()
        if locator_by == "xpath" and "text()" in locator_value:
            score += 10
            reasons.append("Text-based XPath (stable if text doesn't change)")
        else:
            score += 5
            reasons.append("No text-based matching")
        
        # Generate recommendation
        recommendation = self._generate_recommendation(score, locator_by, locator_value, reasons)
        
        return {
            "locator": f"{locator_by}='{locator_value}'",
            "stability_score": score,
            "max_score": 100,
            "stability_level": self._score_to_level(score),
            "reasons": reasons,
            "recommendation": recommendation,
            "breakage_risk": "low" if score >= 70 else "medium" if score >= 40 else "high",
        }
    
    def _score_to_level(self, score):
        if score >= 80:
            return "excellent"
        elif score >= 60:
            return "good"
        elif score >= 40:
            return "fair"
        else:
            return "poor"
    
    def _generate_recommendation(self, score, by, value, reasons):
        if score >= 70:
            return "Locator is stable. No changes needed."
        
        recommendations = []
        
        if by != "id" and "ID-based" not in str(reasons):
            recommendations.append("Consider using an ID if the element has one")
        
        if any("numeric" in r.lower() or "auto-generated" in r.lower() for r in reasons):
            recommendations.append("Request a semantic name from developers (e.g., 'start-btn' instead of 'btn-123')")
        
        if any("deep xpath" in r.lower() for r in reasons):
            recommendations.append("Use a shorter XPath or CSS selector")
        
        if any("many matches" in r.lower() for r in reasons):
            recommendations.append("Add more specificity (e.g., combine class with parent element)")
        
        if not recommendations:
            recommendations.append("Consider adding data-test-id attribute for stable testing")
        
        return " | ".join(recommendations)
    
    def analyze_fingerprints(self, fingerprint_path=None):
        """Analyze all fingerprints and return stability scores."""
        if fingerprint_path is None:
            fingerprint_path = config.POMODORO_FINGERPRINTS_PATH
        
        try:
            with open(fingerprint_path, "r") as f:
                fingerprints = json.load(f)
        except Exception:
            return []
        
        analyses = []
        for element_id, fp in fingerprints.items():
            locator_by = fp.get("healed_locator_by", "css selector")
            locator_value = fp.get("healed_locator_value", f"#{fp.get('element_id', element_id)}")
            
            analysis = self.analyze_locator(locator_by, locator_value)
            analysis["element_id"] = element_id
            analyses.append(analysis)
        
        return analyses


class FlakyTestDetector:
    """Detect tests that heal frequently (likely flaky)."""
    
    def __init__(self, heal_state_path=None):
        self.heal_state_path = heal_state_path or os.path.join(config.DATA_DIR, "heal_state.json")
    
    def load_heal_history(self):
        """Load heal history from the UI heals bucket."""
        heals = store.read("ui_heals")
        return heals if heals else []
    
    def detect_flaky_locators(self, threshold=3):
        """Identify locators that have healed more than threshold times."""
        heals = self.load_heal_history()
        
        # Count heals per locator
        locator_counts = Counter(h.get("broken_selector", "unknown") for h in heals)
        
        flaky = []
        for locator, count in locator_counts.items():
            if count >= threshold:
                # Get details of heals for this locator
                locator_heals = [h for h in heals if h.get("broken_selector") == locator]
                avg_confidence = sum(h.get("confidence_score", 0) for h in locator_heals) / len(locator_heals)
                
                flaky.append({
                    "locator": locator,
                    "heal_count": count,
                    "avg_confidence": round(avg_confidence, 2),
                    "first_heal": locator_heals[0].get("timestamp", "unknown"),
                    "last_heal": locator_heals[-1].get("timestamp", "unknown"),
                    "severity": "high" if count >= 5 else "medium",
                    "recommendation": self._generate_flaky_recommendation(locator, count, avg_confidence),
                })
        
        return sorted(flaky, key=lambda x: x["heal_count"], reverse=True)
    
    def _generate_flaky_recommendation(self, locator, count, avg_confidence):
        if count >= 5:
            return f"Locator '{locator}' has healed {count} times. Consider: (1) requesting a stable data-test-id from developers, (2) using a more semantic locator, or (3) marking this test as expected to heal."
        elif avg_confidence < 50:
            return f"Locator '{locator}' heals with low confidence ({avg_confidence}%). The element may have changed significantly. Verify the golden fingerprint is still accurate."
        else:
            return f"Locator '{locator}' heals frequently but with good confidence. Monitor for further degradation."
    
    def detect_flaky_tests(self, test_heal_map=None):
        """Identify tests that have multiple flaky locators."""
        if test_heal_map is None:
            # Default: group by locator (since we don't have test names in heals)
            return self.detect_flaky_locators()
        
        # If test_heal_map is provided: {test_name: [locator1, locator2, ...]}
        flaky_tests = []
        for test_name, locators in test_heal_map.items():
            flaky_locators = [loc for loc in locators if self._is_locator_flaky(loc)]
            if flaky_locators:
                flaky_tests.append({
                    "test_name": test_name,
                    "flaky_locator_count": len(flaky_locators),
                    "flaky_locators": flaky_locators,
                    "severity": "high" if len(flaky_locators) >= 3 else "medium",
                })
        
        return sorted(flaky_tests, key=lambda x: x["flaky_locator_count"], reverse=True)
    
    def _is_locator_flaky(self, locator, threshold=3):
        heals = self.load_heal_history()
        count = sum(1 for h in heals if h.get("broken_selector") == locator)
        return count >= threshold


class HealCostAnalyzer:
    """Calculate time and cost savings from self-healing."""
    
    # Industry benchmarks (minutes per manual fix)
    MANUAL_FIX_TIME_MINUTES = {
        "simple_locator": 5,
        "complex_locator": 15,
        "debug_and_fix": 30,
    }
    
    def __init__(self):
        self.heals = store.read("ui_heals") or []
    
    def calculate_time_savings(self, manual_fix_minutes=10):
        """Calculate time saved by self-healing vs manual fixing."""
        if not self.heals:
            return {
                "total_heals": 0,
                "time_saved_minutes": 0,
                "time_saved_hours": 0,
                "avg_heal_time_ms": 0,
                "manual_time_minutes": 0,
                "roi_percentage": 0,
            }
        
        total_heals = len(self.heals)
        avg_heal_time_ms = sum(h.get("ms", 35) for h in self.heals) / total_heals
        
        # Time spent by self-healing system (in minutes)
        auto_heal_time_minutes = (avg_heal_time_ms * total_heals) / 1000 / 60
        
        # Time that would have been spent manually
        manual_time_minutes = total_heals * manual_fix_minutes
        
        # Time saved
        time_saved_minutes = manual_time_minutes - auto_heal_time_minutes
        time_saved_hours = time_saved_minutes / 60
        
        # ROI calculation
        roi_percentage = (time_saved_minutes / manual_time_minutes * 100) if manual_time_minutes > 0 else 0
        
        return {
            "total_heals": total_heals,
            "avg_heal_time_ms": round(avg_heal_time_ms, 2),
            "auto_heal_time_minutes": round(auto_heal_time_minutes, 2),
            "manual_time_minutes": manual_time_minutes,
            "time_saved_minutes": round(time_saved_minutes, 2),
            "time_saved_hours": round(time_saved_hours, 2),
            "roi_percentage": round(roi_percentage, 2),
            "assumption": f"Assumes {manual_fix_minutes} minutes per manual fix",
        }
    
    def calculate_cost_savings(self, hourly_rate=50, manual_fix_minutes=10):
        """Calculate cost savings based on engineer hourly rate."""
        time_savings = self.calculate_time_savings(manual_fix_minutes)
        
        cost_saved = (time_savings["time_saved_hours"]) * hourly_rate
        
        return {
            **time_savings,
            "hourly_rate": hourly_rate,
            "cost_saved_usd": round(cost_saved, 2),
            "cost_per_heal_usd": round(cost_saved / time_savings["total_heals"], 2) if time_savings["total_heals"] > 0 else 0,
        }
    
    def generate_report(self):
        """Generate a comprehensive cost analysis report."""
        time_savings = self.calculate_time_savings()
        cost_savings = self.calculate_cost_savings()
        
        # Breakdown by confidence level
        high_confidence = [h for h in self.heals if h.get("confidence_score", 0) >= 75]
        medium_confidence = [h for h in self.heals if 50 <= h.get("confidence_score", 0) < 75]
        low_confidence = [h for h in self.heals if h.get("confidence_score", 0) < 50]
        
        report = {
            "summary": {
                "total_heals": time_savings["total_heals"],
                "time_saved_hours": time_savings["time_saved_hours"],
                "cost_saved_usd": cost_savings["cost_saved_usd"],
                "roi_percentage": time_savings["roi_percentage"],
            },
            "breakdown": {
                "high_confidence_heals": len(high_confidence),
                "medium_confidence_heals": len(medium_confidence),
                "low_confidence_heals": len(low_confidence),
            },
            "efficiency": {
                "avg_heal_time_ms": time_savings["avg_heal_time_ms"],
                "heals_per_hour": round(3600000 / time_savings["avg_heal_time_ms"], 1) if time_savings["avg_heal_time_ms"] > 0 else 0,
                "manual_fixes_per_hour": 6,  # 60 min / 10 min per fix
            },
            "comparison": {
                "self_healing": {
                    "time_per_fix_ms": time_savings["avg_heal_time_ms"],
                    "requires_human": False,
                    "scales_linearly": True,
                },
                "manual": {
                    "time_per_fix_minutes": 10,
                    "requires_human": True,
                    "scales_linearly": False,
                },
            },
        }
        
        return report


def run_analytics():
    """Run all analytics and return combined results."""
    stability_analyzer = LocatorStabilityAnalyzer()
    flaky_detector = FlakyTestDetector()
    cost_analyzer = HealCostAnalyzer()
    
    results = {
        "locator_stability": stability_analyzer.analyze_fingerprints(),
        "flaky_locators": flaky_detector.detect_flaky_locators(),
        "cost_analysis": cost_analyzer.generate_report(),
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    return results


if __name__ == "__main__":
    import json
    
    results = run_analytics()
    
    print("\n" + "="*70)
    print("ADVANCED ANALYTICS REPORT")
    print("="*70)
    
    print("\n📊 LOCATOR STABILITY ANALYSIS")
    print("-" * 70)
    for analysis in results["locator_stability"][:5]:  # Top 5
        print(f"\n{analysis['locator']}")
        print(f"  Stability: {analysis['stability_score']}/100 ({analysis['stability_level']})")
        print(f"  Risk: {analysis['breakage_risk']}")
        print(f"  Recommendation: {analysis['recommendation']}")
    
    print("\n\n🔍 FLAKY LOCATOR DETECTION")
    print("-" * 70)
    if results["flaky_locators"]:
        for flaky in results["flaky_locators"][:5]:  # Top 5
            print(f"\n{flaky['locator']}")
            print(f"  Heal count: {flaky['heal_count']}")
            print(f"  Avg confidence: {flaky['avg_confidence']}%")
            print(f"  Severity: {flaky['severity']}")
            print(f"  Recommendation: {flaky['recommendation']}")
    else:
        print("No flaky locators detected (threshold: 3 heals)")
    
    print("\n\n💰 COST ANALYSIS")
    print("-" * 70)
    cost = results["cost_analysis"]["summary"]
    print(f"Total heals: {cost['total_heals']}")
    print(f"Time saved: {cost['time_saved_hours']:.1f} hours")
    print(f"Cost saved: ${cost['cost_saved_usd']:.2f}")
    print(f"ROI: {cost['roi_percentage']:.1f}%")
    
    efficiency = results["cost_analysis"]["efficiency"]
    print(f"\nAvg heal time: {efficiency['avg_heal_time_ms']}ms")
    print(f"Heals per hour: {efficiency['heals_per_hour']}")
    print(f"Manual fixes per hour: {efficiency['manual_fixes_per_hour']}")
    
    # Save to file
    output_path = os.path.join(config.DATA_DIR, "analytics_report.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n\nFull report saved to: {output_path}")
