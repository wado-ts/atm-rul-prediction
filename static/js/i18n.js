// static/js/i18n.js
/** Client-side i18n for language switching without page reload (optional enhancement) */

class I18nClient {
    constructor() {
        this.lang = this.detectLanguage();
        this.translations = {};
        this.listeners = new Set();
    }

    detectLanguage() {
        // Check HTML lang attribute first (set by server middleware)
        const htmlLang = document.documentElement.lang;
        if (htmlLang && (htmlLang === 'en' || htmlLang === 'fr')) return htmlLang;
        
        // Check cookie (must match middleware cookie name)
        const cookieLang = document.cookie.match(/locale=([^;]+)/);
        if (cookieLang && (cookieLang[1] === 'en' || cookieLang[1] === 'fr')) return cookieLang[1];
        
        // Check localStorage
        const saved = localStorage.getItem('lang');
        if (saved && (saved === 'en' || saved === 'fr')) return saved;
        
        // Fallback to browser language
        if (navigator.language.startsWith('fr')) return 'fr';
        return 'en';
    }

    async loadTranslations(lang) {
        try {
            const response = await fetch(`/static/locales/${lang}.json`);
            if (!response.ok) throw new Error('Failed to load translations');
            this.translations = await response.json();
            this.lang = lang;
            this.notifyListeners();
        } catch (e) {
            console.error('Failed to load translations:', e);
        }
    }

    async switchLanguage(lang) {
        if (lang === this.lang) return;
        
        // Update cookie (must match middleware cookie name)
        document.cookie = `locale=${lang}; path=/; max-age=31536000; SameSite=Lax`;
        
        // Reload with query parameter to ensure middleware picks it up
        const url = new URL(window.location);
        url.searchParams.set('lang', lang);
        window.location.href = url.toString();
    }

    t(key, params = {}) {
        const keys = key.split('.');
        let value = this.translations;
        for (const key of keys) {
            if (value && typeof value === 'object' && key in value) {
                value = value[key];
            } else {
                return key; // fallback to key
            }
        }

        // Simple interpolation
        if (typeof value === 'string') {
            return value.replace(/\{\{(\w+)\}\}/g, (match, key) => params[key] ?? match);
        }
        return value;
    }

    onLanguageChange(callback) {
        this.listeners.add(callback);
    }

    notifyListeners() {
        this.listeners.forEach(cb => cb(this.lang));
    }

    applyTranslations() {
        // Find all elements with data-i18n attribute
        const elements = document.querySelectorAll('[data-i18n]');
        
        elements.forEach(el => {
            const key = el.getAttribute('data-i18n');
            const translation = this.t(key);
            if (translation && translation !== key) {
                el.textContent = translation;
            }
        });

        // Handle placeholders
        const placeholderElements = document.querySelectorAll('[data-i18n-placeholder]');
        
        placeholderElements.forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            const translation = this.t(key);
            if (translation && translation !== key) {
                el.placeholder = translation;
            }
        });
    }
}

const i18n = new I18nClient();

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    const savedLang = document.documentElement.lang || 
                      (navigator.language.startsWith('fr') ? 'fr' : 'en');
    
    console.log('Detected language on DOMContentLoaded:', savedLang);
    console.log('HTML lang attribute:', document.documentElement.lang);
    
    // Load translations
    await i18n.loadTranslations(savedLang);
    
    // Apply translations to the page
    i18n.applyTranslations();
    
    // Initialize language switcher buttons
    const langButtons = document.querySelectorAll('.lang-btn');
    langButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const lang = e.currentTarget.dataset.lang;
            console.log('Language switch button clicked:', lang);
            i18n.switchLanguage(lang);
        });
    });
});

// Export for modules
window.i18n = i18n;
window.t = (key, params) => i18n.t(key, params);