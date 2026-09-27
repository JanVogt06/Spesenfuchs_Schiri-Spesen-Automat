import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import '@/index.css';
import './instagram.css';
import {Slides} from './Slides';

createRoot(document.getElementById('root')!).render(
    <StrictMode>
        <Slides/>
    </StrictMode>,
);
