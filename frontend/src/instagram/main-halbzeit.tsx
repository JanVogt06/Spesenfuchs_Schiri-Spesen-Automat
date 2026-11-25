import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import '@/index.css';
import './instagram.css';
import {Halbzeit} from './Halbzeit';

createRoot(document.getElementById('root')!).render(
    <StrictMode>
        <Halbzeit/>
    </StrictMode>,
);
