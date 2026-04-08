'use client';
import { useState, useEffect, useCallback } from 'react';
import { type Locale, detectLocale } from '@/lib/i18n';

const LOCALE_KEY = 'preferred-locale';

export function useLocale() {
  const [locale, setLocale] = useState<Locale>('en');

  useEffect(() => {
    const stored = localStorage.getItem(LOCALE_KEY) as Locale | null;
    setLocale(stored || detectLocale());
  }, []);

  const changeLocale = useCallback((newLocale: Locale) => {
    setLocale(newLocale);
    localStorage.setItem(LOCALE_KEY, newLocale);
  }, []);

  return { locale, changeLocale };
}
