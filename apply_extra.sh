#!/usr/bin/bash

bsdtar -xf unityhub.deb 'data.tar.*'
tar -xf data.tar.bz2 --strip-components=3 ./opt/unityhub
rm data.tar.* unityhub.deb

patch-resources resources/app.asar

touch chrome-sandbox
chmod +x chrome-sandbox
