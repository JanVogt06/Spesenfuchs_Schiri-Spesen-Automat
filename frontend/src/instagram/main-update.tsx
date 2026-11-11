import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import '@/index.css';
import './instagram.css';
import {Update} from './Update';

createRoot(document.getElementById('root')!).render(
    <StrictMode>
        <Update/>
    </StrictMode>,
);
