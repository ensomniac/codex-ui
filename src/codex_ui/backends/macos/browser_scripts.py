"""Chrome JXA discovery and activation payloads. No remote debugging port."""

CHROME_QUERY_JXA = r"""
const chrome = Application("Google Chrome");
const running = chrome.running();
const tabs = [];

if (running) {
    chrome.windows().forEach((window) => {
        try {
            const bounds = window.bounds();
            const activeTabIndex = window.activeTabIndex();
            let windowId = null;
            try { windowId = window.id(); } catch (error) {}
            window.tabs().forEach((tab, tabOffset) => {
                tabs.push({
                    windowIndex: window.index(),
                    windowId,
                    tabIndex: tabOffset + 1,
                    activeTabIndex,
                    title: tab.title(),
                    url: tab.url(),
                    bounds,
                    visible: window.visible(),
                    minimized: window.minimized(),
                });
            });
        } catch (error) {
            // A tab or window can disappear while Chrome is queried.
        }
    });
}

JSON.stringify({running, tabs});
"""


CHROME_ACTIVE_QUERY_JXA = r"""
const chrome = Application("Google Chrome");
const running = chrome.running();
const tabs = [];

if (running) {
    chrome.windows().forEach((window) => {
        try {
            const bounds = window.bounds();
            const activeTabIndex = window.activeTabIndex();
            const tab = window.activeTab();
            let windowId = null;
            try { windowId = window.id(); } catch (error) {}
            tabs.push({
                windowIndex: window.index(),
                windowId,
                tabIndex: activeTabIndex,
                activeTabIndex,
                title: tab.title(),
                url: tab.url(),
                bounds,
                visible: window.visible(),
                minimized: window.minimized(),
            });
        } catch (error) {
            // A tab or window can disappear while Chrome is queried.
        }
    });
}

JSON.stringify({running, tabs});
"""


CHROME_ACTIVATE_JXA = r"""
function run(argv) {
    const chrome = Application("Google Chrome");
    if (!chrome.running()) throw new Error("Google Chrome is not running");
    const windowIndex = Number(argv[0]);
    const tabIndex = Number(argv[1]);
    const windowId = Number(argv[2]);
    const windows = chrome.windows();
    let window = Number.isFinite(windowId) && windowId > 0
        ? windows.find((candidate) => candidate.id() === windowId)
        : null;
    if (!window) window = windows[windowIndex - 1];
    if (!window) throw new Error("Chrome target window disappeared");
    window.minimized = false;
    window.visible = true;
    window.activeTabIndex = tabIndex;
    window.index = 1;
    chrome.activate();
    const selected = window.activeTab();
    return JSON.stringify({
        windowId: window.id(),
        tabIndex: window.activeTabIndex(),
        title: selected.title(),
        url: selected.url(),
    });
}
"""


CHROME_DEVELOPER_MENU_JXA = r"""
function run(argv) {
    const itemName = String(argv[0]);
    const events = Application("System Events");
    const chrome = events.processes.byName("Google Chrome");
    const developer = chrome.menuBars[0]
        .menuBarItems.byName("View").menus[0]
        .menuItems.byName("Developer").menus[0];
    const item = developer.menuItems.byName(itemName);
    if (!item.exists()) throw new Error(`Chrome Developer menu item not found: ${itemName}`);
    if (!item.enabled()) throw new Error(`Chrome Developer menu item is disabled: ${itemName}`);
    item.click();
    return JSON.stringify({clicked: itemName});
}
"""
