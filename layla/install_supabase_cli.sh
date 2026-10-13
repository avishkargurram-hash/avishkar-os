#!/bin/sh
set -e
cd /tmp
VERSION=$(curl -s https://api.github.com/repos/supabase/cli/releases/latest | grep -o '"tag_name": *"v[^"]*"' | cut -d'"' -f4)
echo "Latest supabase CLI version: $VERSION"
curl -sL "https://github.com/supabase/cli/releases/download/${VERSION}/supabase_linux_amd64.tar.gz" -o supabase.tar.gz
tar -xzf supabase.tar.gz
mv supabase /usr/local/bin/supabase
chmod +x /usr/local/bin/supabase
rm -f supabase.tar.gz
supabase --version
