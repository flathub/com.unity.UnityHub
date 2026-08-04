#!/usr/bin/bash

bsdtar -xf unityhub.deb 'data.tar.*'
tar -xf data.tar.zst --strip-components=4 ./usr/lib/unityhub
rm data.tar.* unityhub.deb

patch-resources resources/app.asar

touch chrome-sandbox
chmod +x chrome-sandbox
