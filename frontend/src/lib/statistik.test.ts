import {beforeEach, describe, expect, it, vi} from 'vitest';
import {apiGet, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import {getStatistik, monatsName} from './statistik';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

beforeEach(() => apiZuruecksetzen());

describe('statistik', () => {
    it('fragt die Saison als Parameter ab', async () => {
        getRouten({'/api/statistik': {saison: '25/26'}});
        await expect(getStatistik('25/26')).resolves.toMatchObject({saison: '25/26'});
        expect(apiGet).toHaveBeenCalledWith('/api/statistik', {params: {saison: '25/26'}});
    });

    it('benennt Monate kurz und laesst Unbrauchbares stehen', () => {
        expect(monatsName('2026-09')).toBe('Sept. 2026');
        expect(monatsName('kaputt')).toBe('kaputt');
    });
});
