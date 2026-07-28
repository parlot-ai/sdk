import React, {type ReactNode} from 'react';
import OriginalNavbarLayout from '@theme-original/Navbar/Layout';
import type {Props} from '@theme/Navbar/Layout';

export default function NavbarLayout(props: Props): ReactNode {
  return <OriginalNavbarLayout {...props} />;
}
