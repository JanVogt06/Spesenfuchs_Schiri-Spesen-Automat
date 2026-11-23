import {beforeEach, describe, expect, it, vi} from 'vitest';
import {apiGet, apiZuruecksetzen, getRouten} from '@/test/apiMock';
import {getStammdaten} from './stammdaten';

vi.mock('@/lib/api', async () => (await import('@/test/apiMock')).apiModul);

beforeEach(() => {
    apiZuruecksetzen();
});

describe('getStammdaten', () => {
    it('laedt /api/stammdaten und reicht auch unbekannte Felder durch', async () => {
        getRouten({'/api/stammdaten': {name_vorname: 'Muster, Max', neues_feld: 'ja'}});

        await expect(getStammdaten()).resolves.toEqual({name_vorname: 'Muster, Max', neues_feld: 'ja'});
        expect(apiGet).toHaveBeenCalledWith('/api/stammdaten');
    });

    it('liefert vor dem ersten Abruf null statt eines Fehlers', async () => {
        getRouten({'/api/stammdaten': null});

        await expect(getStammdaten()).resolves.toBeNull();
    });
});
