const getAppIdFromUrl = (): string => {
    const url = window.location.href;
    const match = url.match(/\/custom_applications\/([^/]+)/);
    return match ? match[1] : '';
};

/**
 * Creates a prefixed key in the format /custom_applications/{id}/{key}
 */
const getPrefixedKey = (key: string): string => {
    const appId = getAppIdFromUrl();
    return appId ? `/custom_applications/${appId}/${key}` : key;
};

export const getStorageItem = (key: string): string | null => {
    return localStorage.getItem(getPrefixedKey(key));
};

export const setStorageItem = (key: string, value: string): void => {
    localStorage.setItem(getPrefixedKey(key), value);
};
