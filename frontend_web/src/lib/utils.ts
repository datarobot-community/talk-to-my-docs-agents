import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
export * from './ttmdocs-utils';

const ROOT_FONT_SIZE = 14;

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

function toFixed(number: number, precision: number) {
    const multiplier = Math.pow(10, precision + 1),
        wholeNumber = Math.floor(number * multiplier);
    return (Math.round(wholeNumber / 10) * 10) / multiplier;
}

export function pxToRem(
    px: number | string,
    rootValue: number = ROOT_FONT_SIZE,
    unitPrecision: number = 5,
    minPixelValue: number = 0.01
): string {
    if (!px) {
        return '';
    }
    const pixels = typeof px === 'string' ? parseFloat(px) : (px as number);
    if (pixels < minPixelValue) {
        return typeof px === 'string' ? px : `${px}px`;
    }
    const fixedVal = toFixed(pixels / rootValue, unitPrecision);
    return fixedVal + 'rem';
}

export function remToPx(
    rem: number | string,
    rootValue: number = ROOT_FONT_SIZE,
    unitPrecision: number = 5
): number {
    if (!rem) {
        return 0;
    }
    const value = typeof rem === 'string' ? parseFloat(rem) : (rem as number);
    const fixedVal = toFixed(value * rootValue, unitPrecision);
    return fixedVal;
}

function getCookieValue(name: string): string | null {
    if (typeof document === 'undefined') {
        return null;
    }
    const cookies = document.cookie.split('; ');
    for (const cookie of cookies) {
        const separatorIndex = cookie.indexOf('=');
        if (separatorIndex === -1) {
            continue;
        }
        const key = cookie.slice(0, separatorIndex);
        if (key === name) {
            return cookie.slice(separatorIndex + 1);
        }
    }
    return null;
}

export function getCookieBoolean(name: string, fallback: boolean): boolean {
    const value = getCookieValue(name);
    return value ? value === 'true' : fallback;
}

export function getCookieNumber(name: string, fallback: number): number {
    const value = getCookieValue(name);
    return value ? parseFloat(value) : fallback;
}

export function getCookieString(name: string, fallback: string): string {
    const value = getCookieValue(name);
    return value || fallback;
}
