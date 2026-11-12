import { PublicHeader } from '../public-header';
import { PublicFooter } from '../public-footer';
import { Mascot } from '../mascot';
import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TuiAppearance, TuiButton, TuiLink } from '@taiga-ui/core';
import { TuiCardLarge } from '@taiga-ui/layout';
import { TuiBadge } from '@taiga-ui/kit';

@Component({
  selector: 'app-home',
  imports: [
    PublicHeader,
    PublicFooter,
    Mascot,
    RouterLink,
    TuiAppearance,
    TuiButton,
    TuiLink,
    TuiCardLarge,
    TuiBadge,
  ],
  templateUrl: './home.html',
  styleUrl: './home.less',
})
export class Home {}
