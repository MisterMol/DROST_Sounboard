# Afhankelijkheden en licenties

DrostSoundboard gebruikt onder andere:

- **pystray**: GNU LGPLv3, https://github.com/moses-palmer/pystray
- **Pillow**: Pillow-licentie (HPND), https://python-pillow.org/
- **NumPy**: BSD-3-Clause, https://numpy.org/
- **python-sounddevice**: MIT, https://python-sounddevice.readthedocs.io/
- **python-soundfile**: BSD-3-Clause; gebruikt libsndfile, https://python-soundfile.readthedocs.io/
- **SoXR / python-soxr**: zie de distributielicenties van de gebruikte SoXR-build, https://github.com/dofuuz/python-soxr
- **imageio-ffmpeg / FFmpeg**: verschillende licenties afhankelijk van de meegeleverde FFmpeg-build. Controleer vóór een gebundelde release onder andere LGPL/GPL en codecvoorwaarden, https://ffmpeg.org/legal.html
- **Velopack**: MIT, wordt voor de Windows-release als updater gebruikt, https://velopack.io/
- **PyInstaller**: GPLv2 met speciale uitzondering voor applicatiebundeling, https://pyinstaller.org/
- **VB-CABLE**: afzonderlijke download, donationware van VB-Audio, https://vb-audio.com/Cable/
- **Signalsmith Stretch 1.3.0 en Signalsmith Linear 0.1.2**: MIT; bronlicenties staan in `app/audio/native/LICENTIES.txt` naast de gebundelde DLL, https://signalsmith-audio.co.uk/code/stretch/
- **LLVC (Koe AI)**: MIT voor de betreffende LLVC-code; licentietekst zit in `stem-runtime/licenses/LLVC-MIT.txt` van het lokale stempakket. Dit zegt **niet automatisch** dat ieder afzonderlijk modelgewicht vrij verspreid mag worden.
- **PyTorch**: BSD-3-Clause; de runtime heeft eigen licentie- en noticebestanden onder `stem-runtime/licenses/torch/`, https://pytorch.org/
- **Stemmodellen en ingebouwde stemvoorbeelden**: controleer de oorspronkelijke herkomst, trainingsmateriaal en toestemmingen afzonderlijk. Een MIT-licentie op code geeft geen automatisch recht om stemopnames of modelgewichten openbaar te verspreiden.


De bibliotheken houden hun eigen auteursrechten en licenties. De MIT-licentie van DrostSoundboard vervangt deze licenties niet. **Voor een publieke gebundelde installer is een volledige controle van de daadwerkelijke distributieartefacten nodig**, inclusief licentieteksten en FFmpeg-binaryconfiguratie.
