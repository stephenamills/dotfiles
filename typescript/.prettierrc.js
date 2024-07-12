/** @type {import("prettier").Config} */
export default {
	printWidth: 100,
	semi: false,
	plugins: ['prettier-plugin-tailwindcss'], // Tailwind CSS must come last https://github.com/tailwindlabs/prettier-plugin-tailwindcss#compatibility-with-other-prettier-plugins
	tailwindConfig: "./tailwind.config.ts"
}
