"""Convert finished preview artwork into the game's two TGA image sizes."""
import argparse
from pathlib import Path

from PIL import Image, ImageOps

KINDS = ('cloverleaf','diamond','trumpet','directional','turbine','stack')
CONTENT = Path(__file__).resolve().parents[1] / 'content' / 'interchanges'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images',nargs='+',help='KIND=PATH to approved artwork')
    args = parser.parse_args()
    sources = []
    for item in args.images:
        kind,separator,path = item.partition('=')
        if not separator or kind not in KINDS:
            parser.error('Expected KIND=PATH with one of: '+', '.join(KINDS))
        with Image.open(path) as image:
            sources.append((kind,image.convert('RGBA')))
    for kind,source in sources:
        for suffix,size in (('',(256,160)),('_preview',(768,480))):
            image = ImageOps.fit(source,size,method=Image.Resampling.LANCZOS)
            image.save(CONTENT / f'{kind}{suffix}@2x.tga',format='TGA',compression=None)
        print(kind)


if __name__ == '__main__':
    main()
