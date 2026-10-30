"""Gerichte signaaltests. Geen getraind model, Windowsaudio of luistertest."""
import io
import unittest
import numpy as np
import soundfile as sf
from app.audio.natuurlijke_stem.voorbeeldaudio import (
    lees_voorbeeld, maak_mono, pas_bronniveau_aan, bereid_voorbeeld_voor)


def wav(audio, rate=48000, subtype='FLOAT'):
    f = io.BytesIO(); sf.write(f, audio, rate, format='WAV', subtype=subtype); return f.getvalue()


def toon(amp=.1, rate=48000, seconden=.2):
    return (amp*np.sin(np.arange(int(rate*seconden))*2*np.pi*180/rate)).astype(np.float32)


class TestVoorbeeldAudio418(unittest.TestCase):
    def test_normaal_niveau_verandert_niet(self):
        x=toon(); np.testing.assert_array_equal(pas_bronniveau_aan(x),x)
    def test_zacht_niveau_hooguit_factor_vier(self):
        x=toon(.004); y=pas_bronniveau_aan(x)
        np.testing.assert_allclose(y,x*4,atol=1e-8)
    def test_stil_blijft_stil(self):
        x=np.zeros(9000,np.float32);np.testing.assert_array_equal(pas_bronniveau_aan(x),x)
    def test_zeer_stille_ruis_niet_versterkt(self):
        x=toon(.00001);np.testing.assert_array_equal(pas_bronniveau_aan(x),x)
    def test_harde_bron_uniform_verlaagd_zonder_afkappen(self):
        x=toon(2);y=pas_bronniveau_aan(x)
        factor=y[30]/x[30];self.assertLess(factor,1);self.assertLessEqual(float(np.max(np.abs(y))),.85001)
        np.testing.assert_allclose(y,x*factor,atol=2e-7)
    def test_extra_stilte_verandert_gain_niet(self):
        x=toon(.015,seconden=.4);y=np.concatenate([np.zeros(9600,np.float32),x,np.zeros(9600,np.float32)])
        np.testing.assert_allclose(pas_bronniveau_aan(x),pas_bronniveau_aan(y)[9600:-9600],atol=1e-6)
    def test_stereokanalen_gelijk_behouden(self):
        x=toon();np.testing.assert_array_equal(maak_mono(np.column_stack([x,x])),x)
    def test_tegenfase_verdwijnt_niet_in_monogemiddelde(self):
        x=toon();np.testing.assert_array_equal(maak_mono(np.column_stack([x,-x])),x)
    def test_stille_kant_gewoon_gemengd(self):
        x=toon();np.testing.assert_allclose(maak_mono(np.column_stack([x,np.zeros_like(x)])),x*.5)
    def test_mono_ongewijzigd(self):
        x=toon();np.testing.assert_array_equal(maak_mono(x[:,None]),x)
    def test_alles_blijft_float32(self):
        self.assertEqual(bereid_voorbeeld_voor(wav(toon())).dtype,np.float32)
    def test_geen_opname_of_model_bij_bronvoorbereiding(self):
        result=bereid_voorbeeld_voor(wav(toon()));self.assertEqual(result.shape,(9600,))
    def test_samplefrequenties_correcte_lengte(self):
        for sr in (16000,22050,44100,48000,96000):
            with self.subTest(sr=sr):
                y=bereid_voorbeeld_voor(wav(toon(rate=sr),sr));self.assertLessEqual(abs(len(y)-9600),1)
                self.assertTrue(np.isfinite(y).all());self.assertGreater(np.max(y),.08)
    def test_teveel_kanalen_geweigerd(self):
        with self.assertRaises(ValueError):lees_voorbeeld(wav(np.ones((100,3),np.float32)*.1))
    def test_te_lang_geweigerd(self):
        with self.assertRaises(ValueError):lees_voorbeeld(wav(np.zeros(16000*31,np.float32),16000))
    def test_lege_audio_geweigerd(self):
        with self.assertRaises(ValueError):lees_voorbeeld(wav(np.zeros(0,np.float32)))
    def test_foute_samplefrequentie_geweigerd(self):
        with self.assertRaises(ValueError):lees_voorbeeld(wav(toon(),4000))
    def test_nan_geweigerd(self):
        x=toon();x[15]=np.nan
        with self.assertRaises(ValueError):lees_voorbeeld(wav(x))
    def test_beschadigd_bestand_niet_als_stilte_aanvaarden(self):
        with self.assertRaises(ValueError):lees_voorbeeld(b'niet-echt-wav'*20)
    def test_fouttype_en_overmaat_geweigerd(self):
        for x in (None,{},bytearray(b'a'*100),b'a'*(12*1024*1024+1)):
            with self.subTest(type=type(x)),self.assertRaises(ValueError):lees_voorbeeld(x)
    def test_bronarray_niet_gewijzigd(self):
        x=toon(.02);before=x.copy();pas_bronniveau_aan(x);np.testing.assert_array_equal(x,before)

if __name__=='__main__':unittest.main()
