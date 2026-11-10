import { Brand } from '../brand';
import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TuiAppearance, TuiButton, TuiIcon, TuiLink } from '@taiga-ui/core';
import { TuiCardLarge } from '@taiga-ui/layout';

@Component({
  selector: 'app-home',
  imports: [Brand, RouterLink, TuiAppearance, TuiButton, TuiIcon, TuiLink, TuiCardLarge],
  templateUrl: './home.html',
  styleUrl: './home.less',
})
export class Home {}
