/* @refresh reload */
import { render } from 'solid-js/web';
import App from './App';
import './styles.css';
import { branding } from './config';

// Set dynamic page title based on agent
document.title = branding.title;

const root = document.getElementById('root');

if (!root) {
  throw new Error('Root element not found');
}

render(() => <App />, root);
